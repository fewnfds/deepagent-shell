from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
import sqlite3
import threading
from typing import Any

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
from agent_shell.storage.autos import AutoStore
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
        ("workflows", ("id", "public_id", "payload", "revision", "enabled")),
        ("auto_roots", ("id", "payload", "revision")),
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
    _autos: AutoStore
    _runtime: AgentRuntime
    _preparation: WorkflowPreparationRuntime
    _database: _SnapshotDatabase

    def main_agent_by_name(self, name: str) -> dict[str, Any] | None:
        return self._configs.get_item_by_name("main_agents", name)

    def workflow_by_id(self, workflow_id: str) -> dict[str, Any] | None:
        return self._workflows.get_item(workflow_id)

    def workflow_by_public_id(self, public_id: str) -> dict[str, Any] | None:
        return self._workflows.get_item_by_public_id(public_id)

    def root_target(self, public_id: str) -> dict[str, Any] | None:
        workflow = self.workflow_by_public_id(public_id)
        if workflow is not None and workflow.get("enabled", True):
            return {"kind": "workflow", "id": str(workflow["id"]), "record": workflow}
        main_agent = self._configs.get_item_by_public_id(public_id)
        if main_agent is not None:
            return {"kind": "agent", "id": str(main_agent["id"]), "record": main_agent}
        return None

    async def resolve_root_target(
        self, public_id: str, messages: object
    ) -> dict[str, Any] | None:
        auto = self._autos.get_item_by_public_id(public_id)
        if auto is not None and auto.get("enabled", True):
            from agent_shell.auto.resolver import resolve_auto_source

            selected = await resolve_auto_source(str(auto.get("source", "")), messages)
            target = self.root_target(selected["public_id"])
            if target is None or target["kind"] != selected["kind"]:
                raise AgentRuntimeError(
                    "auto.target_not_found",
                    "The Auto routing target does not exist or has the wrong kind.",
                    status_code=404,
                )
            target["auto_id"] = str(auto.get("id", ""))
            return target
        return self.root_target(public_id)

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
        preparation = await self._preparation.prepare(
            definition,
            request_id=request_id,
            messages=validate_client_messages(raw_messages),
        )
        if artifact_committer is not None:
            artifact_committer.rule = preparation.artifact_rule
            artifact_committer.transform = preparation.artifact_transform
            artifact_committer.minimum_text_bytes = (
                preparation.artifact_minimum_text_bytes
            )

        workspace = None
        base = record.get("agent_base")
        if isinstance(base, dict):
            source = base.get("source")
            if isinstance(source, dict) and isinstance(source.get("id"), str):
                workspace = self._runtime.prepare_workspace(str(source["id"]))
        if workspace is None:
            for node in record.get("nodes", []):
                if isinstance(node, dict) and node.get("type") == "builtin.agent.call":
                    agent_id = node.get("config", {}).get("agent_id")
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

        async def invoke_agent(
            agent_id: str,
            messages: list[Any],
            _context: WorkflowContext,
        ) -> str:
            normalized = [
                {
                    "role": (
                        "assistant"
                        if message.__class__.__name__ == "AIMessage"
                        else "user"
                    ),
                    "content": getattr(message, "content", str(message)),
                }
                for message in messages
            ]
            execution = await self._runtime.start(
                agent_id,
                normalized,
                request_id=request_id,
                public_model=str(record.get("public_id", "")),
                artifact_committer=artifact_committer,
                workspace=workspace,
            )
            content, _usage = await execution.run()
            return content

        async def invoke_tool(
            tool_name: str,
            arguments: dict[str, Any],
            _state: dict[str, Any],
            _context: WorkflowContext,
        ) -> Any:
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
            raise AgentRuntimeError(
                "workflow.tool_unavailable",
                "The requested Workflow tool is unavailable.",
                status_code=422,
            )

        compiler = WorkflowCompiler(
            workflow_lookup=self.workflow_by_id,
            agent_lookup=lambda agent_id: self._configs.get_item("main_agents", agent_id),
            agent_invoker=invoke_agent,
            tool_invoker=invoke_tool,
        )
        compiled = compiler.compile(record)
        return WorkflowExecution(
            compiled=compiled,
            input_state={
                "messages": preparation.messages,
                "files": dict(workspace.initial_files) if workspace is not None else {},
            },
            context=WorkflowContext(
                request_id=request_id,
                workflow_id=workflow_id,
                invocation_id=invocation_id or request_id,
            ),
            artifact_events=artifact_events if artifact_events is not None else [],
            close=self.close,
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
    ) -> None:
        self._database = database
        self._custom_tools_dir = custom_tools_dir
        self._automation_scripts_dir = automation_scripts_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._diagnostics = diagnostics
        self._provider_http_clients = provider_http_clients
        self._media_outputs = media_outputs

    def capture(self) -> RequestRuntimeSnapshot:
        database = _SnapshotDatabase(self._database)
        try:
            blocks = BlockStore(database)  # type: ignore[arg-type]
            configs = AgentConfigStore(database)  # type: ignore[arg-type]
            workflows = WorkflowStore(database)  # type: ignore[arg-type]
            autos = AutoStore(database)  # type: ignore[arg-type]
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
                _autos=autos,
                _runtime=runtime,
                _preparation=preparation,
                _database=database,
            )
            holder["snapshot"] = snapshot
            return snapshot
        except Exception:
            database.close()
            raise
