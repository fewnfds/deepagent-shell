from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from langchain.chat_models import init_chat_model
from pydantic import SecretStr

from agent_shell import __version__
from agent_shell.middleware_packages.runtime import MiddlewarePackageRuntime
from agent_shell.capability_manifest import FILESYSTEM_TOOL_NAMES
from agent_shell.contracts import (
    FilesystemBlock,
    FilesystemPermissionsBlock,
    OutputModeBlock,
    PromptCachingBlock,
    SkillBlock,
    SummarizationBlock,
)
from agent_shell.provider_http import PROVIDER_HTTP_TIMEOUT, ProviderHttpClients
from agent_shell.provider_secrets import ProviderCredentialError, ProviderSecretResolver
from agent_shell.plugins.workflow_input_context.factory import (
    materialize_workflow_input_context_middleware,
)
from agent_shell.runtime.capabilities import (
    DeepAgentsCapabilityError,
    DeepAgentsWorkspace,
    build_deepagents_capabilities,
)
from agent_shell.runtime.capabilities.custom_tools import materialize_custom_tools
from agent_shell.runtime.capabilities.exception_retry import (
    configure_model_for_retry,
    materialize_exception_retry,
    model_block_with_retry_overrides,
)
from agent_shell.runtime.capabilities.prompt_caching import (
    disabled_prompt_caching_middleware,
    materialize_prompt_caching_middleware,
)
from agent_shell.runtime.capabilities.summarization import (
    disabled_summarization_middleware,
    materialize_summarization_middleware,
)
from agent_shell.runtime.capabilities.todo_list import disabled_todo_list_middleware
from agent_shell.runtime.agent_compilation import (
    MaterializedAgentProfile,
    configuration_error,
    construct_deep_agent,
    reported_error,
    validate_middleware_names,
    validate_model_visible_tool_names,
)
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.input_messages import validate_client_messages
from agent_shell.runtime.limits import (
    ProviderErrorBoundaryMiddleware,
    ToolErrorBoundaryMiddleware,
)
from agent_shell.runtime.model_request_settings import (
    make_model_request_settings_middleware,
)
from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.state import AgentShellState
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


@dataclass(frozen=True, slots=True)
class BuiltAgent:
    graph: Any
    input_state: dict[str, Any]
    output_config: dict[str, Any]
    agent_id: str
    agent_name: str
    subagent_profile_ids: dict[str, str]
    middleware_runtime: MiddlewarePackageRuntime
    workspace: DeepAgentsWorkspace | None = None


class AgentBuilder:
    def __init__(
        self,
        secrets: ProviderSecretResolver,
        *,
        custom_tools_dir: Path,
        middleware_packages_dir: Path,
        runtime_dir: Path,
        skills_dir: Path,
        validation: ConfigurationValidationService,
        provider_http_clients: ProviderHttpClients,
    ) -> None:
        self._secrets = secrets
        self._custom_tools_dir = custom_tools_dir
        self._middleware_packages_dir = middleware_packages_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._validation = validation
        self._provider_http_clients = provider_http_clients
        self._middleware_runtime: MiddlewarePackageRuntime | None = None

    async def close_failed_build(self) -> None:
        if self._middleware_runtime is None:
            return
        await self._middleware_runtime.close()

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
        disabled_capabilities: frozenset[str] = frozenset(),
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

        elif "todo-list" in disabled_capabilities:
            middleware.append(disabled_todo_list_middleware())

        backend = None
        initial_files: dict[str, Any] = {}
        skill_sources: tuple[str, ...] = ()
        filesystem = selected_blocks.get("filesystem")
        filesystem_permissions = selected_blocks.get("filesystem-permissions")
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
            filesystem_permissions_block = (
                FilesystemPermissionsBlock.model_validate(
                    {
                        key: value
                        for key, value in filesystem_permissions.items()
                        if key != "id"
                    }
                )
                if filesystem_permissions is not None
                else None
            )
            deepagents = build_deepagents_capabilities(
                filesystem_block,
                skill_block,
                filesystem_permissions=filesystem_permissions_block,
                filesystem_mode=filesystem_mode,
                skills_dir=self._skills_dir,
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
                    else "workflow.filesystem_id"
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
                    else "workflow.filesystem_id"
                ),
            ) from exc
        backend = deepagents.backend
        middleware.extend(deepagents.middleware)
        initial_files.update(deepagents.initial_files)
        skill_sources = deepagents.skill_sources

        extra_middleware: list[Any] = []
        workflow_input_context = selected_blocks.get("workflow-input-context")
        if workflow_input_context is not None:
            try:
                input_context_middleware = materialize_workflow_input_context_middleware(
                    {
                        key: value
                        for key, value in workflow_input_context.items()
                        if key != "id"
                    },
                    backend=backend,
                    scope=scope,
                )
                if input_context_middleware is not None:
                    extra_middleware.append(input_context_middleware)
            except Exception as exc:
                raise configuration_error(
                    "middleware_materialization_failed",
                    "The selected Workflow input context configuration could not be constructed.",
                    status_code=422,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.workflow-input-context",
                ) from exc

        summarization = selected_blocks.get("summarization")
        if summarization is not None:
            try:
                summarization_block = SummarizationBlock.model_validate(
                    {
                        key: value
                        for key, value in summarization.items()
                        if key != "id"
                    }
                )
                extra_middleware.append(
                    materialize_summarization_middleware(
                        summarization_block,
                        model=model,
                        backend=backend,
                    )
                )
            except Exception as exc:
                raise configuration_error(
                    "middleware_materialization_failed",
                    "The selected summarization configuration could not be constructed.",
                    status_code=422,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.summarization",
                ) from exc
        elif "summarization" in disabled_capabilities:
            extra_middleware.append(disabled_summarization_middleware())

        prompt_caching = selected_blocks.get("prompt-caching")
        if prompt_caching is not None:
            try:
                prompt_caching_block = PromptCachingBlock.model_validate(
                    {
                        key: value
                        for key, value in prompt_caching.items()
                        if key != "id"
                    }
                )
                extra_middleware.append(
                    materialize_prompt_caching_middleware(prompt_caching_block)
                )
            except Exception as exc:
                raise configuration_error(
                    "middleware_materialization_failed",
                    "The selected prompt-caching configuration could not be constructed.",
                    status_code=422,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="capability_refs.prompt-caching",
                ) from exc
        elif "prompt-caching" in disabled_capabilities:
            extra_middleware.append(disabled_prompt_caching_middleware())

        package_middleware: tuple[Any, ...] = ()
        if self._middleware_runtime is not None:
            try:
                package_middleware = self._middleware_runtime.middleware_for(owner_id)
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
            package_middleware=package_middleware,
            extra_middleware=tuple(extra_middleware),
            backend=backend,
            initial_files=initial_files,
            skill_sources=skill_sources,
            permissions=deepagents.permissions,
            workspace=deepagents.workspace,
        )

    async def build(
        self,
        main_agent_id: str,
        raw_messages: object,
        *,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], Any] | None = None,
        request_id: str = "",
        workflow_filesystem_id: str | None = None,
        workspace: DeepAgentsWorkspace | None = None,
    ) -> BuiltAgent:
        # Validate the immutable request snapshot before any selected user module
        # can be imported or any optional capability can be materialized.
        messages = validate_client_messages(raw_messages)
        report, assembly = self._validation.resolve_main_agent(
            main_agent_id,
            workflow_filesystem_id=workflow_filesystem_id,
        )
        if not report.valid:
            issue = report.issues[0]
            if issue.code == "assembly.main_agent_not_found":
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
        main_agent = assembly.main_agent
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

        main_agent_id = str(main_agent.get("id", main_agent_id))
        main_agent_name = str(main_agent["name"])
        middleware_runtime = MiddlewarePackageRuntime.from_assembly(
            assembly,
            main_agent_id=main_agent_id,
            request_id=request_id,
            packages_dir=self._middleware_packages_dir,
            runtime_root=self._runtime_dir,
        )
        self._middleware_runtime = middleware_runtime
        materialized = self._materialize_profile(
            references,
            selected_blocks,
            filesystem_mode=assembly.filesystem_mode,
            scope="main_agent",
            owner_id=main_agent_id,
            owner_name=main_agent_name,
            workspace=workspace,
            disabled_capabilities=assembly.disabled_capabilities,
        )
        constructor: dict[str, object] = {
            "model": materialized.model,
            "name": str(main_agent["name"]),
            "state_schema": AgentShellState,
            "context_schema": WorkflowRuntimeContext,
        }
        if materialized.system_prompt is not None:
            constructor["system_prompt"] = materialized.system_prompt
        if materialized.tools:
            constructor["tools"] = list(materialized.tools)
        if materialized.response_format is not None:
            constructor["response_format"] = materialized.response_format
        if materialized.backend is not None:
            constructor["backend"] = materialized.backend
        if materialized.permissions:
            constructor["permissions"] = list(materialized.permissions)
        if materialized.skill_sources:
            constructor["skills"] = list(materialized.skill_sources)

        middleware = [
            ToolErrorBoundaryMiddleware(),
            *materialized.middleware,
            *materialized.package_middleware,
        ]
        if materialized.tool_choice is not None or materialized.model_settings:
            middleware.append(
                make_model_request_settings_middleware(
                    tool_choice=materialized.tool_choice,
                    model_settings=materialized.model_settings,
                )
            )
        input_state: dict[str, Any] = {"messages": [], "shared_vars": {}}

        compiled_subagents: list[dict[str, Any]] = []
        task_description_override: str | None = None
        if resolved_subagents:
            from agent_shell.runtime.subagents import build_subagent_specs

            compiled_subagents = build_subagent_specs(
                roots=resolved_subagents,
                nodes=assembly.subagent_nodes,
                workspace=materialized.workspace,
                materialize_profile=self._materialize_profile,
            )
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

        middleware.extend(materialized.extra_middleware)
        if model_request_observer is not None:
            from agent_shell.runtime.interception import (
                make_model_request_observer_middleware,
            )

            middleware.append(
                make_model_request_observer_middleware(
                    model_request_observer,
                    context={
                        "agent_type": "main_agent",
                        "agent_name": main_agent_name,
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
            validate_middleware_names(middleware, owner="Main Agent")
            main_agent_middleware_names = {
                getattr(item, "name", None) for item in middleware
            }
            validate_model_visible_tool_names(
                tools=materialized.tools,
                middleware=middleware,
                owner="Main Agent",
                default_tool_names=(
                    ()
                    if "FilesystemMiddleware" in main_agent_middleware_names
                    else FILESYSTEM_TOOL_NAMES
                )
                + (
                    ("task",)
                    if resolved_subagents
                    and "SubAgentMiddleware" not in main_agent_middleware_names
                    else ()
                ),
            )
        except AgentRuntimeError as exc:
            raise reported_error(
                exc,
                scope="main_agent",
                owner_id=main_agent_id,
                owner_name=main_agent_name,
                path="capability_refs",
            ) from exc

        if middleware:
            constructor["middleware"] = middleware

        graph = construct_deep_agent(
            constructor,
            model_provider=materialized.model_provider,
            model_name=materialized.model_name,
            scope="main_agent",
            owner_id=main_agent_id,
            owner_name=main_agent_name,
            subject="Main Agent",
            path="capability_refs",
        )

        return BuiltAgent(
            graph=graph,
            input_state=input_state,
            output_config=output_config,
            agent_id=main_agent_id,
            agent_name=str(main_agent["name"]),
            subagent_profile_ids={
                node.name: node.key for node in assembly.subagent_nodes.values()
            },
            middleware_runtime=middleware_runtime,
            workspace=materialized.workspace,
        )
