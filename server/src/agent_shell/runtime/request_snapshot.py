from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
import sqlite3
import threading
from typing import Any, Callable

from agent_shell.provider_http import ProviderHttpClients
from agent_shell.provider_secrets import ProviderSecretResolver
from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.runtime.agent_runtime import AgentExecution, AgentRuntime
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.storage.entry_scripts import EntryScriptStore
from agent_shell.workflow.artifacts import ArtifactCommitter
from agent_shell.workflow.preparation import WorkflowPreparationRuntime
from agent_shell.storage.schema import SCHEMA_SQL
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.validation.service import ConfigurationValidationService


class _SnapshotDatabase:
    """Private query-only image of one committed configuration view."""

    _TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("provider_secrets", ("id", "secret_value")),
        ("blocks", ("id", "block_type", "name", "payload")),
        ("main_agents", ("id", "name", "payload")),
        ("subagents", ("id", "component_name", "payload")),
        ("workflows", ("id", "payload", "revision", "enabled")),
        ("entry_scripts", ("id", "payload", "revision")),
    )

    def __init__(self, source: SQLiteDatabase) -> None:
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = sqlite3.connect(
            ":memory:", check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA_SQL)
        with source.transaction() as source_connection:
            source_connection.execute("BEGIN")
            for table, columns in self._TABLES:
                names = ", ".join(columns)
                rows = source_connection.execute(
                    f"SELECT {names} FROM {table}"
                ).fetchall()
                if rows:
                    placeholders = ", ".join("?" for _ in columns)
                    self._connection.executemany(
                        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                        [tuple(row[column] for column in columns) for row in rows],
                    )
        self._connection.commit()
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA query_only = ON")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            if connection is None:
                raise RuntimeError("request configuration snapshot is closed")
            yield connection

    def close(self) -> None:
        with self._lock:
            connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter timing varies
        try:
            self.close()
        except Exception:
            pass


@dataclass(slots=True)
class RequestRuntimeSnapshot:
    """Resolve a model and build exactly one request from one database image."""

    _configs: AgentConfigStore
    _workflows: WorkflowStore
    _entry_scripts: EntryScriptStore
    _runtime: AgentRuntime
    _preparation: WorkflowPreparationRuntime
    _database: _SnapshotDatabase
    _plugins_dir: Path
    _runtime_root: Path
    _checkpointer_provider: Callable[[], Any] | None = None

    def main_agent_by_name(self, name: str) -> dict[str, Any] | None:
        return self._configs.get_item_by_name("main_agents", name)

    def workflow_by_id(self, workflow_id: str) -> dict[str, Any] | None:
        return self._workflows.get_item(workflow_id)

    def root_target(self, model_name: str) -> dict[str, Any] | None:
        entry = self._entry_scripts.get_item_by_name(model_name)
        if entry is not None and entry.get("enabled", True):
            workflow = self.workflow_by_id(str(entry["graph_id"]))
            if workflow is not None and workflow.get("enabled", True):
                return {"kind": "workflow", "id": str(workflow["id"]), "record": workflow, "entry": entry}
        return None

    async def resolve_root_target(
        self, model_name: str, messages: object
    ) -> dict[str, Any] | None:
        return self.root_target(model_name)

    async def start_agent(
        self,
        main_agent_id: str,
        raw_messages: object,
        **kwargs: Any,
    ) -> AgentExecution:
        try:
            return await self._runtime.start(main_agent_id, raw_messages, **kwargs)
        finally:
            # Agent construction has materialized every database-backed dependency.
            # Closing here makes any accidental lazy configuration read fail.
            self._database.close()

    async def start_workflow(
        self,
        workflow_id: str,
        raw_messages: object,
        *,
        request_id: str = "",
        invocation_id: str = "",
        artifact_committer: ArtifactCommitter | None = None,
        artifact_events: list[dict[str, Any]] | None = None,
        entry_script: dict[str, Any] | None = None,
    ):
        from agent_shell.runtime.input_messages import validate_client_messages
        from agent_shell.runtime.workflow_execution import WorkflowExecution
        from agent_shell.workflow.compiler import WorkflowCompiler
        from agent_shell.workflow.context import WorkflowContext
        from agent_shell.workflow.contracts import WorkflowDefinition

        record = self.workflow_by_id(workflow_id)
        if record is None:
            raise AgentRuntimeError(
                "workflow_not_found",
                "The requested Workflow does not exist.",
                status_code=404,
            )

        payload = {
            key: value
            for key, value in record.items()
            if key not in {"id", "revision"}
        }
        try:
            definition = WorkflowDefinition.model_validate(payload)
        except Exception as exc:
            raise AgentRuntimeError(
                "workflow.validation_failed",
                "The Workflow definition is invalid.",
                status_code=422,
            ) from exc
        client_messages = validate_client_messages(raw_messages)
        entry_variables: dict[str, Any] = {}
        entry_state: dict[str, Any] = {}
        if entry_script is not None and isinstance(entry_script.get("source"), str) and entry_script["source"].strip():
            namespace: dict[str, Any] = {"__builtins__": __builtins__}
            try:
                exec(compile(entry_script["source"], "<entry-script>", "exec"), namespace, namespace)
                prepare = namespace.get("prepare")
                if not callable(prepare):
                    raise ValueError("entry script must define prepare(messages)")
                result = prepare(client_messages)
                if not isinstance(result, dict):
                    raise ValueError("entry script prepare must return an object")
                if isinstance(result.get("messages"), list):
                    client_messages = validate_client_messages(result["messages"])
                for key in ("inputs", "shared", "control", "artifacts", "ports", "output"):
                    value = result.get(key)
                    if isinstance(value, dict):
                        entry_state[key] = dict(value)
                entry_variables = dict(entry_state.get("shared") or {})
            except AgentRuntimeError:
                raise
            except Exception as exc:
                raise AgentRuntimeError("entry_script_failed", "The Entry Script failed during preparation.", status_code=422) from exc
        preparation = await self._preparation.prepare(
            definition,
            request_id=request_id,
            messages=client_messages,
        )
        if artifact_committer is not None:
            artifact_committer.rule = preparation.artifact_rule
            artifact_committer.transform = preparation.artifact_transform
            artifact_committer.minimum_text_bytes = (
                preparation.artifact_minimum_text_bytes
            )

        workspace = None
        for node in record.get("nodes", []):
            if isinstance(node, dict) and node.get("type") == "builtin.agent":
                agent_id = node.get("config", {}).get("profile_id")
                if isinstance(agent_id, str) and agent_id:
                    workspace = self._runtime.prepare_workspace(agent_id)
                    break

        if preparation.initial_files:
            if workspace is None:
                workspace = self._runtime.create_workspace()
            from deepagents.backends.utils import create_file_data
            import base64

            for path, content in preparation.initial_files.items():
                if (
                    not isinstance(path, str)
                    or not path.startswith("/")
                    or str(PurePosixPath(path)) != path
                    or ".." in PurePosixPath(path).parts
                ):
                    raise AgentRuntimeError(
                        "workflow.preparation_invalid_file",
                        "Workflow preparation produced an invalid virtual file path.",
                        status_code=422,
                    )
                if isinstance(content, bytes):
                    value = create_file_data(
                        base64.b64encode(content).decode("ascii"), encoding="base64"
                    )
                elif isinstance(content, str):
                    value = create_file_data(content)
                else:
                    raise AgentRuntimeError(
                        "workflow.preparation_invalid_file",
                        "Workflow preparation files must be text or bytes.",
                        status_code=422,
                    )
                workspace.initial_files[path] = value

        compiled = await self.compile_workflow(
            workflow_id,
            raw_messages=list(preparation.messages),
            workspace=workspace,
            artifact_committer=artifact_committer,
            request_id=request_id,
        )
        return WorkflowExecution(
            compiled=compiled,
            input_state={
                "messages": preparation.messages,
                "inputs": {"messages": preparation.messages, **dict(entry_state.get("inputs") or {})},
                "shared": {**entry_variables, **dict(preparation.variables)},
                "artifacts": {},
                "messages": preparation.messages,
                **{key: value for key, value in entry_state.items() if key not in {"inputs", "shared"}},
            },
            context=WorkflowContext(
                request_id=request_id,
                workflow_id=workflow_id,
                invocation_id=invocation_id or request_id,
                agent_contexts=compiled.agent_contexts,
            ),
            thread_id=invocation_id or request_id,
            artifact_events=artifact_events if artifact_events is not None else [],
            close=None,
        )

    async def compile_workflow(
        self,
        workflow_id: str,
        *,
        event_sink: Any = None,
        checkpointer: Any = None,
        raw_messages: list[dict[str, Any]] | None = None,
        workspace: Any = None,
        artifact_committer: ArtifactCommitter | None = None,
        request_id: str = "",
    ):
        """Materialize one fixed Graph for a background Graph Run."""
        from agent_shell.workflow.compiler import WorkflowCompiler
        from agent_shell.workflow.context import WorkflowContext
        from agent_shell.workflow.compiler import AgentNodeRuntime
        from agent_shell.workflow.state import WorkflowState
        from agent_shell.workflow.catalog import scan_workflow_node_registry
        from agent_shell.automation.loader import AutomationPluginLoader
        from agent_shell.workflow.plugin_context import WorkflowNodeContext

        record = self.workflow_by_id(workflow_id)
        if record is None:
            raise AgentRuntimeError("workflow_not_found", "The requested Graph does not exist.", status_code=404)
        if checkpointer is None and self._checkpointer_provider is not None:
            checkpointer = self._checkpointer_provider()
        node_registry = scan_workflow_node_registry(self._plugins_dir, runtime_root=self._runtime_root)
        plugin_loader = AutomationPluginLoader(
            request_id=request_id or workflow_id,
            plugins_dir=self._plugins_dir,
            runtime_root=self._runtime_root,
        )
        if workspace is None:
            workspace = None
        agent_nodes: dict[tuple[str, str], AgentNodeRuntime] = {}
        built_agents: list[Any] = []
        for node in record.get("nodes", []):
            if isinstance(node, dict) and node.get("type") == "builtin.agent":
                profile_id = node.get("config", {}).get("profile_id")
                if isinstance(profile_id, str) and profile_id:
                    if workspace is None:
                        workspace = self._runtime.prepare_workspace(profile_id)
                    built = await self._runtime.build_graph(
                        profile_id,
                        list(raw_messages or []),
                        artifact_committer=artifact_committer,
                        workspace=workspace,
                        request_id=f"{request_id}:{node.get('id', profile_id)}" if request_id else str(node.get("id", profile_id)),
                        state_schema=WorkflowState,
                        context_key=str(node.get("id", profile_id)),
                    )
                    built_agents.append(built)
                    agent_nodes[(workflow_id, str(node.get("id", profile_id)))] = AgentNodeRuntime(
                        graph=built.graph,
                        input_state=built.input_state,
                        context=built.context,
                        start=built.automation.start,
                        finish=built.automation.finish,
                    )

        async def invoke_agent(agent_id: str, messages: list[Any], context: WorkflowContext) -> str:
            normalized = [{"role": "assistant" if message.__class__.__name__ == "AIMessage" else "user", "content": getattr(message, "content", str(message))} for message in messages]
            execution = await self._runtime.start(agent_id, normalized, request_id=context.request_id, public_model=str(record.get("name", workflow_id)), workspace=workspace)
            content, _usage = await execution.run()
            return content

        async def invoke_tool(tool_name: str, arguments: dict[str, Any], _state: dict[str, Any], _context: WorkflowContext) -> Any:
            if tool_name == "echo":
                return arguments.get("text", "")
            if tool_name == "commit" and artifact_committer is not None:
                path = arguments.get("path")
                if not isinstance(path, str):
                    return {"status": "failed", "code": "invalid_path"}
                try:
                    return await artifact_committer.commit(path)
                except Exception as exc:
                    return {
                        "status": "failed",
                        "code": getattr(exc, "code", "commit_failed"),
                        "message": str(exc),
                    }
            raise AgentRuntimeError("workflow.tool_unavailable", "The requested Graph tool is unavailable.", status_code=422)

        async def invoke_plugin(node: Any, node_definition: Any, inputs: Mapping[str, Any], state: Any, context: WorkflowContext) -> Any:
            if not node_definition.plugin_id or not node_definition.entrypoint:
                raise AgentRuntimeError("workflow.plugin_invalid", "The Workflow node plugin descriptor is invalid.", status_code=422)
            module, metadata, _plugin_dir = plugin_loader.load(
                node.id,
                "workflow-node",
                0,
                node_definition.plugin_id,
            )
            contribution = next(
                (
                    item
                    for item in metadata.get("workflow_nodes", [])
                    if isinstance(item, dict) and item.get("type") == node.type
                ),
                None,
            )
            function = getattr(module, node_definition.entrypoint, None)
            if contribution is None or not callable(function):
                raise AgentRuntimeError("workflow.plugin_entrypoint_invalid", "The Workflow node plugin entrypoint is invalid.", status_code=422)
            result = await function(
                WorkflowNodeContext(
                    node_id=node.id,
                    node_type=node.type,
                    config=node.config,
                    inputs=inputs,
                    state=state,
                    runtime=context,
                )
            )
            return result

        compiler = WorkflowCompiler(
            workflow_lookup=self.workflow_by_id,
            agent_lookup=lambda agent_id: self._configs.get_item("main_agents", agent_id),
            agent_invoker=invoke_agent,
            tool_invoker=invoke_tool,
            event_sink=event_sink,
            checkpointer=checkpointer,
            agent_nodes=agent_nodes,
            node_catalog={item.type: item for item in node_registry.all()},
            plugin_invoker=invoke_plugin,
        )
        try:
            compiled = compiler.compile(record)
        except Exception:
            for built in reversed(built_agents):
                await built.automation.finish({"status": "failed", "error_code": "workflow_compile_failed"})
            self.close()
            raise
        def cleanup() -> None:
            plugin_loader.close()
            self.close()

        return compiled.__class__(
            compiled.id,
            compiled.name,
            compiled.definition,
            compiled.graph,
            cleanup=cleanup,
            agent_contexts=compiled.agent_contexts,
            start=compiled.start,
            finish=compiled.finish,
        )

    def close(self) -> None:
        self._database.close()

    def compiled_workflow_subagent(self, workflow_id: str) -> dict[str, Any]:
        from agent_shell.runtime.workflow_adapters import as_compiled_subagent
        from agent_shell.workflow.compiler import WorkflowCompiler
        from agent_shell.workflow.context import WorkflowContext

        record = self.workflow_by_id(workflow_id)
        if record is None:
            raise AgentRuntimeError(
                "workflow_not_found",
                "The requested Workflow does not exist.",
                status_code=404,
            )

        async def invoke_agent(agent_id: str, messages: list[Any], context: WorkflowContext) -> str:
            normalized = [
                {
                    "role": "assistant" if message.__class__.__name__ == "AIMessage" else "user",
                    "content": getattr(message, "content", str(message)),
                }
                for message in messages
            ]
            execution = await self._runtime.start(
                agent_id,
                normalized,
                request_id=context.request_id,
                public_model=context.workflow_id,
            )
            content, _usage = await execution.run()
            return content

        async def invoke_tool(tool_name: str, arguments: dict[str, Any], _state: dict[str, Any], _context: WorkflowContext) -> Any:
            if tool_name == "echo":
                return arguments.get("text", "")
            raise AgentRuntimeError(
                "workflow.tool_unavailable",
                "The requested Workflow tool is unavailable.",
                status_code=422,
            )

        compiled = WorkflowCompiler(
            workflow_lookup=self.workflow_by_id,
            agent_lookup=lambda agent_id: self._configs.get_item("main_agents", agent_id),
            agent_invoker=invoke_agent,
            tool_invoker=invoke_tool,
        ).compile(record)
        return as_compiled_subagent(compiled, description=str(record.get("description", "")))


class RequestSnapshotRuntime:
    """Capture the latest committed configuration for each Agent construction."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        custom_tools_dir: Path,
        automation_scripts_dir: Path,
        runtime_dir: Path,
        skills_dir: Path,
        diagnostics: RuntimeDiagnostics,
        provider_http_clients: ProviderHttpClients,
        media_outputs: MediaOutputStore,
        checkpointer_provider: Callable[[], Any] | None = None,
    ) -> None:
        self._database = database
        self._custom_tools_dir = custom_tools_dir
        self._automation_scripts_dir = automation_scripts_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._diagnostics = diagnostics
        self._provider_http_clients = provider_http_clients
        self._media_outputs = media_outputs
        self._checkpointer_provider = checkpointer_provider

    def capture(self) -> RequestRuntimeSnapshot:
        database = _SnapshotDatabase(self._database)
        try:
            blocks = BlockStore(database)  # type: ignore[arg-type]
            configs = AgentConfigStore(database)  # type: ignore[arg-type]
            workflows = WorkflowStore(database)  # type: ignore[arg-type]
            secrets = ProviderSecretResolver(database)  # type: ignore[arg-type]
            automation_validation = AutomationValidationService(
                scripts_dir=self._automation_scripts_dir,
                runtime_root=self._runtime_dir,
            )
            validation = ConfigurationValidationService(
                blocks,
                configs,
                automation_validation,
                custom_tools_dir=self._custom_tools_dir,
                workflow_lookup=workflows.get_item,
            )
            preparation = WorkflowPreparationRuntime(
                plugins_dir=self._automation_scripts_dir,
                runtime_root=self._runtime_dir,
                skills_dir=self._skills_dir,
            )
            holder: dict[str, RequestRuntimeSnapshot] = {}
            runtime = AgentRuntime(
                AgentBuilder(
                    secrets,
                    custom_tools_dir=self._custom_tools_dir,
                    automation_scripts_dir=self._automation_scripts_dir,
                    runtime_dir=self._runtime_dir,
                    skills_dir=self._skills_dir,
                    validation=validation,
                    provider_http_clients=self._provider_http_clients,
                    workflow_provider=lambda workflow_id: holder["snapshot"].compiled_workflow_subagent(workflow_id),
                ),
                self._media_outputs,
                self._diagnostics,
            )
            snapshot = RequestRuntimeSnapshot(
                _configs=configs,
            _workflows=workflows,
            _entry_scripts=EntryScriptStore(database),
                _runtime=runtime,
                _preparation=preparation,
                _database=database,
                _plugins_dir=self._automation_scripts_dir,
                _runtime_root=self._runtime_dir,
                _checkpointer_provider=self._checkpointer_provider,
            )
            holder["snapshot"] = snapshot
            return snapshot
        except Exception:
            database.close()
            raise
