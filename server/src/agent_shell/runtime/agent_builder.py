from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from langchain.chat_models import init_chat_model
from pydantic import SecretStr

from agent_shell import __version__
from agent_shell.automation.runtime import AutomationRuntime
from agent_shell.capability_manifest import FILESYSTEM_TOOL_NAMES
from agent_shell.contracts import FilesystemBlock, OutputModeBlock, SkillBlock
from agent_shell.provider_http import PROVIDER_HTTP_TIMEOUT, ProviderHttpClients
from agent_shell.provider_secrets import ProviderCredentialError, ProviderSecretResolver
from agent_shell.runtime.capabilities import (
    DeepAgentsCapabilityError,
    DeepAgentsWorkspace,
    build_deepagents_capabilities,
)
from agent_shell.runtime.capabilities.custom_middlewares import (
    materialize_custom_middlewares,
)
from agent_shell.runtime.capabilities.custom_tools import materialize_custom_tools
from agent_shell.runtime.capabilities.exception_retry import (
    configure_model_for_retry,
    materialize_exception_retry,
    model_block_with_retry_overrides,
)
from agent_shell.runtime.agent_compilation import (
    MaterializedAgentProfile,
    configuration_error,
    construct_deep_agent,
    reported_error,
    validate_middleware_names,
    validate_model_visible_tool_names,
)
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.limits import (
    ProviderErrorBoundaryMiddleware,
    ToolErrorBoundaryMiddleware,
)
from agent_shell.runtime.model_request_settings import (
    make_model_request_settings_middleware,
)
from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.subagent_input import AgentRequestContext
from agent_shell.validation.capability_assembly import FilesystemMode
from agent_shell.validation.service import ConfigurationValidationService


_OPENAI_COMPATIBLE_PROVIDERS = frozenset({"deepseek", "openai", "xai"})


def _build_chat_model(
    block: dict[str, Any],
    credential: str | None,
    provider_http_clients: ProviderHttpClients,
):
    provider = str(block["provider"])
    try:
        kwargs: dict[str, object] = {
            "base_url": block["base_url"],
            **dict(block["provider_settings"]),
        }
        if provider == "google_vertexai":
            if credential:
                raise ValueError(
                    "google_vertexai uses Application Default Credentials"
                )
        else:
            kwargs["api_key"] = SecretStr(
                credential or "agent-shell-no-credential"
            )
        if provider in _OPENAI_COMPATIBLE_PROVIDERS:
            kwargs.setdefault("timeout", PROVIDER_HTTP_TIMEOUT)
            kwargs.update(
                {
                    "default_headers": {
                        "User-Agent": f"Agent-Shell/{__version__}",
                    },
                    "http_client": provider_http_clients.sync_client,
                    "http_async_client": provider_http_clients.async_client,
                }
            )
        return init_chat_model(
            model=str(block["model"]),
            model_provider=provider,
            **kwargs,
        )
    except ImportError as exc:
        raise AgentRuntimeError(
            "model_provider_adapter_unavailable",
            "The selected LangChain Provider integration is not installed.",
            status_code=503,
        ) from exc
    except Exception as exc:
        raise AgentRuntimeError(
            "model_configuration_invalid",
            "The selected model configuration cannot construct its Provider adapter.",
            status_code=422,
        ) from exc


def validate_openai_messages(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AgentRuntimeError(
            "input_messages_required",
            "messages must be a non-empty array.",
            status_code=422,
        )
    messages: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AgentRuntimeError(
                "input_message_invalid",
                f"messages[{index}] must be an object.",
                status_code=422,
            )
        role = item.get("role")
        content = item.get("content")
        if role not in {"system", "user", "assistant"}:
            raise AgentRuntimeError(
                "input_message_role_unsupported",
                f"messages[{index}].role is not supported by the current text runtime.",
                status_code=422,
            )
        if not isinstance(content, str):
            raise AgentRuntimeError(
                "input_message_content_unsupported",
                f"messages[{index}].content must be a string in the current text runtime.",
                status_code=422,
            )
        message = {"role": role, "content": content}
        name = item.get("name")
        if name is not None:
            if not isinstance(name, str) or not name:
                raise AgentRuntimeError(
                    "input_message_name_invalid",
                    f"messages[{index}].name must be a non-empty string.",
                    status_code=422,
                )
            message["name"] = name
        messages.append(message)
    return messages


@dataclass(frozen=True, slots=True)
class BuiltAgent:
    graph: Any
    input_state: dict[str, Any]
    output_config: dict[str, Any]
    agent_name: str
    context: AgentRequestContext
    automation: AutomationRuntime


class AgentBuilder:
    def __init__(
        self,
        secrets: ProviderSecretResolver,
        *,
        custom_tools_dir: Path,
        automation_scripts_dir: Path,
        runtime_dir: Path,
        skills_dir: Path,
        validation: ConfigurationValidationService,
        provider_http_clients: ProviderHttpClients,
    ) -> None:
        self._secrets = secrets
        self._custom_tools_dir = custom_tools_dir
        self._automation_scripts_dir = automation_scripts_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._validation = validation
        self._provider_http_clients = provider_http_clients
        self._automation_runtime: AutomationRuntime | None = None

    async def finish_failed_build(self) -> None:
        if self._automation_runtime is None:
            return
        await self._automation_runtime.finish(
            {"status": "failed", "error_code": "agent_construction_failed"}
        )

    def _materialize_profile(
        self,
        references: dict[str, str],
        selected_blocks: dict[str, dict[str, Any]],
        *,
        filesystem_mode: FilesystemMode,
        scope: str,
        owner_id: str,
        owner_name: str,
        workspace: DeepAgentsWorkspace | None = None,
    ) -> MaterializedAgentProfile:
        model_id = references["model"]
        model_block = selected_blocks["model"]
        exception_retry = selected_blocks.get("exception-retry")
        effective_model_block = (
            model_block_with_retry_overrides(model_block, exception_retry)
            if exception_retry is not None
            else model_block
        )
        try:
            credential = self._secrets.resolve_model(model_id)
        except ProviderCredentialError as exc:
            raise configuration_error(
                exc.code,
                exc.safe_message,
                status_code=409,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path="capability_refs.model",
            ) from exc
        try:
            model = _build_chat_model(
                effective_model_block,
                credential,
                self._provider_http_clients,
            )
            if exception_retry is not None:
                model = configure_model_for_retry(model, exception_retry)
        except AgentRuntimeError as exc:
            raise reported_error(
                exc,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path="capability_refs.model",
            ) from exc
        except Exception as exc:
            raise configuration_error(
                "model_configuration_invalid",
                "The selected model configuration could not be constructed.",
                status_code=422,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path="capability_refs.model",
            ) from exc

        tools: list[Any] = []
        custom_tool = selected_blocks.get("custom-tool")
        if custom_tool is not None and custom_tool["tools"]:
            try:
                tools.extend(
                    materialize_custom_tools(
                        custom_tool["tools"],
                        directory=self._custom_tools_dir,
                    )
                )
            except AgentRuntimeError as exc:
                raise reported_error(
                    exc,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.custom-tool",
                ) from exc

        middleware: list[Any] = []
        todo = selected_blocks.get("todo-list")
        if todo is not None:
            try:
                from langchain.agents.middleware import TodoListMiddleware

                todo_kwargs: dict[str, str] = {}
                if todo["system_prompt_override"] is not None:
                    todo_kwargs["system_prompt"] = todo["system_prompt_override"]
                if todo["tool_description_override"] is not None:
                    todo_kwargs["tool_description"] = todo["tool_description_override"]
                middleware.append(TodoListMiddleware(**todo_kwargs))
            except Exception as exc:
                raise configuration_error(
                    "middleware_materialization_failed",
                    "The selected Todo capability could not be constructed.",
                    status_code=422,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.todo-list",
                ) from exc

        backend = None
        initial_files: dict[str, Any] = {}
        skill_sources: tuple[str, ...] = ()
        filesystem = selected_blocks.get("filesystem")
        skill = selected_blocks.get("skill")
        try:
            filesystem_block = (
                FilesystemBlock.model_validate(
                    {
                        key: value
                        for key, value in filesystem.items()
                        if key != "id"
                    }
                )
                if filesystem is not None
                else None
            )
            skill_block = (
                SkillBlock.model_validate(
                    {key: value for key, value in skill.items() if key != "id"}
                )
                if skill is not None
                else None
            )
            selected_skill_names = (
                list(skill_block.skills) if skill_block is not None else []
            )
            effective_skills_dir = (
                self._automation_runtime.effective_skills_dir(
                    owner_id, selected_skill_names
                )
                if self._automation_runtime is not None
                else self._skills_dir
            )
            deepagents = build_deepagents_capabilities(
                filesystem_block,
                skill_block,
                filesystem_mode=filesystem_mode,
                skills_dir=effective_skills_dir,
                workspace=workspace,
            )
        except DeepAgentsCapabilityError as exc:
            raise configuration_error(
                "middleware_materialization_failed",
                "The selected filesystem or Skill capability could not be constructed.",
                status_code=422,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=(
                    "capability_refs.skill"
                    if skill is not None
                    else "capability_refs.filesystem"
                ),
            ) from exc
        except Exception as exc:
            raise configuration_error(
                "middleware_materialization_failed",
                "The selected filesystem or Skill configuration is invalid.",
                status_code=422,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=(
                    "capability_refs.skill"
                    if skill is not None
                    else "capability_refs.filesystem"
                ),
            ) from exc
        backend = deepagents.backend
        middleware.extend(deepagents.middleware)
        initial_files.update(deepagents.initial_files)
        if self._automation_runtime is not None:
            automation_files = self._automation_runtime.initial_files_for(owner_id)
            if automation_files:
                from deepagents.backends.utils import create_file_data

                for path, content in automation_files.items():
                    if not isinstance(path, str) or not path.startswith("/"):
                        raise AgentRuntimeError(
                            "automation_initial_file_invalid",
                            "Automation initial file paths must be absolute virtual paths.",
                            status_code=422,
                        )
                    if isinstance(content, bytes):
                        import base64

                        value = create_file_data(
                            base64.b64encode(content).decode("ascii"),
                            encoding="base64",
                        )
                    elif isinstance(content, str):
                        value = create_file_data(content)
                    else:
                        raise AgentRuntimeError(
                            "automation_initial_file_invalid",
                            "Automation initial file values must be text or bytes.",
                            status_code=422,
                        )
                    initial_files[path] = value
                    deepagents.workspace.initial_files[path] = value
        skill_sources = deepagents.skill_sources

        custom_middleware: list[Any] = []
        custom = selected_blocks.get("custom-middleware")
        if custom is not None:
            try:
                custom_middleware.extend(
                    materialize_custom_middlewares(custom["middlewares"])
                )
            except AgentRuntimeError as exc:
                raise reported_error(
                    exc,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.custom-middleware",
                ) from exc

        system_prompt = selected_blocks.get("system-prompt")
        exception_retry_runtime = (
            materialize_exception_retry(exception_retry)
            if exception_retry is not None
            else None
        )
        return MaterializedAgentProfile(
            model=model,
            model_provider=str(model_block["provider"]),
            model_name=str(model_block["model"]),
            tool_choice=model_block.get("tool_choice"),
            response_format=model_block.get("response_format"),
            model_settings=dict(model_block.get("model_settings") or {}),
            exception_retry=exception_retry_runtime,
            system_prompt=(
                system_prompt["system_prompt"] if system_prompt is not None else None
            ),
            tools=tuple(tools),
            middleware=tuple(middleware),
            custom_middleware=tuple(custom_middleware),
            backend=backend,
            initial_files=initial_files,
            skill_sources=skill_sources,
            workspace=deepagents.workspace,
        )

    async def build(
        self,
        primary_id: str,
        raw_messages: object,
        *,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        agent_input_observer: Callable[[dict[str, object]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], Any] | None = None,
        request_id: str = "",
    ) -> BuiltAgent:
        # Validate the immutable request snapshot before any selected user module
        # can be imported or any optional capability can be materialized.
        messages = validate_openai_messages(raw_messages)
        report, assembly = self._validation.resolve_primary(primary_id)
        if not report.valid:
            issue = report.issues[0]
            if issue.code == "assembly.primary_not_found":
                status_code = 404
            elif issue.code in {
                "assembly.referenced_block_invalid",
                "assembly.tool_name_conflict",
            } or issue.code.startswith("contract."):
                status_code = 422
            else:
                status_code = 409
            raise AgentRuntimeError(
                issue.code,
                issue.message,
                status_code=status_code,
                validation_report=report,
            )
        assert assembly is not None
        primary = assembly.primary
        references = assembly.references
        selected_blocks = assembly.blocks
        output_config = OutputModeBlock.model_validate(
            {
                key: value
                for key, value in selected_blocks["output-mode"].items()
                if key != "id"
            }
        ).model_dump(mode="json")
        resolved_subagents = assembly.subagents

        primary_id = str(primary.get("id", primary_id))
        primary_name = str(primary["name"])
        automation = AutomationRuntime.from_assembly(
            assembly,
            messages,
            primary_id=primary_id,
            request_id=request_id,
            scripts_dir=self._automation_scripts_dir,
            skills_dir=self._skills_dir,
            runtime_root=self._runtime_dir,
        )
        self._automation_runtime = automation
        await automation.prepare()
        prepared_messages = validate_openai_messages(
            automation.messages_for(primary_id)
        )
        if agent_input_observer is not None:
            agent_input_observer(
                {
                    "agent_type": "primary",
                    "agent_name": primary_name,
                    "tool_call_id": "",
                    "message_count": len(prepared_messages),
                }
            )
        materialized = self._materialize_profile(
            references,
            selected_blocks,
            filesystem_mode=assembly.filesystem_mode,
            scope="primary",
            owner_id=primary_id,
            owner_name=primary_name,
        )
        constructor: dict[str, object] = {
            "model": materialized.model,
            "name": str(primary["name"]),
            "context_schema": AgentRequestContext,
        }
        if materialized.system_prompt is not None:
            constructor["system_prompt"] = materialized.system_prompt
        if materialized.tools:
            constructor["tools"] = list(materialized.tools)
        if materialized.response_format is not None:
            constructor["response_format"] = materialized.response_format
        if materialized.backend is not None:
            constructor["backend"] = materialized.backend
        if materialized.skill_sources:
            constructor["skills"] = list(materialized.skill_sources)

        middleware = [ToolErrorBoundaryMiddleware(), *materialized.middleware]
        if materialized.tool_choice is not None or materialized.model_settings:
            middleware.append(
                make_model_request_settings_middleware(
                    tool_choice=materialized.tool_choice,
                    model_settings=materialized.model_settings,
                )
            )
        input_state: dict[str, Any] = {"messages": prepared_messages}
        request_context: AgentRequestContext = {
            "automation_runtime": automation
        }

        compiled_subagents: list[dict[str, Any]] = []
        task_description_override: str | None = None
        if resolved_subagents:
            from agent_shell.runtime.subagent_graphs import SubagentGraphCompiler

            compiled_subagents = SubagentGraphCompiler(
                workspace=materialized.workspace,
                materialize_profile=self._materialize_profile,
                agent_input_observer=agent_input_observer,
            ).compile(roots=resolved_subagents, nodes=assembly.subagent_nodes)
            delegation_instruction = selected_blocks["subagent"][
                "instruction_override"
            ]
            task_description_override = selected_blocks["subagent"][
                "task_description_override"
            ]
            if delegation_instruction is not None:
                existing_prompt = str(constructor.get("system_prompt") or "")
                constructor["system_prompt"] = "\n\n".join(
                    part for part in (existing_prompt, delegation_instruction) if part
                )
            constructor["subagents"] = compiled_subagents

        middleware.extend(materialized.custom_middleware)
        if model_request_observer is not None:
            from agent_shell.runtime.interception import (
                make_model_request_observer_middleware,
            )

            middleware.append(
                make_model_request_observer_middleware(
                    model_request_observer,
                    context={
                        "agent_type": "primary",
                        "agent_name": primary_name,
                        "tool_call_id": "",
                    },
                )
            )
        if model_request_interceptor is not None:
            from agent_shell.runtime.interception import make_interception_middleware

            middleware.append(
                make_interception_middleware(model_request_interceptor)
            )
        exception_retry_runtime = materialized.exception_retry
        middleware.append(ProviderErrorBoundaryMiddleware())
        if exception_retry_runtime is not None:
            middleware.extend(exception_retry_runtime.after_provider_boundary)
        initial_files = dict(materialized.workspace.initial_files)
        if initial_files or resolved_subagents:
            input_state["files"] = initial_files

        try:
            if compiled_subagents and task_description_override is not None:
                from agent_shell.runtime.subagent_middleware import (
                    make_subagent_middleware_override,
                )

                replacement = make_subagent_middleware_override(
                    backend=materialized.backend,
                    subagents=compiled_subagents,
                    task_description=task_description_override,
                    middleware=middleware,
                )
                if replacement is not None:
                    middleware.append(replacement)
            validate_middleware_names(middleware, owner="Primary Agent")
            primary_middleware_names = {
                getattr(item, "name", None) for item in middleware
            }
            validate_model_visible_tool_names(
                tools=materialized.tools,
                middleware=middleware,
                owner="Primary Agent",
                default_tool_names=(
                    ()
                    if "FilesystemMiddleware" in primary_middleware_names
                    else FILESYSTEM_TOOL_NAMES
                )
                + (
                    ("task",)
                    if resolved_subagents
                    and "SubAgentMiddleware" not in primary_middleware_names
                    else ()
                ),
            )
        except AgentRuntimeError as exc:
            raise reported_error(
                exc,
                scope="primary",
                owner_id=primary_id,
                owner_name=primary_name,
                path="capability_refs",
            ) from exc

        if middleware:
            constructor["middleware"] = middleware

        graph = construct_deep_agent(
            constructor,
            model_provider=materialized.model_provider,
            model_name=materialized.model_name,
            scope="primary",
            owner_id=primary_id,
            owner_name=primary_name,
            subject="Primary Agent",
            path="capability_refs",
        )

        return BuiltAgent(
            graph=graph,
            input_state=input_state,
            output_config=output_config,
            agent_name=str(primary["name"]),
            context=request_context,
            automation=automation,
        )
