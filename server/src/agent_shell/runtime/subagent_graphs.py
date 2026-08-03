from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_shell.capability_manifest import FILESYSTEM_TOOL_NAMES
from agent_shell.runtime.deferred_subagent import DeferredSubagentRunnable
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.limits import (
    ProviderErrorBoundaryMiddleware,
    ToolErrorBoundaryMiddleware,
)
from agent_shell.runtime.model_request_settings import (
    make_model_request_settings_middleware,
)
from agent_shell.runtime.subagent_input import AgentRequestContext, SubagentInputMiddleware
from agent_shell.validation.service import (
    ResolvedSubagent,
    ResolvedSubagentEdge,
    SubagentNodeKey,
)


def _compiled_spec(
    edge: ResolvedSubagentEdge,
    runnables: dict[SubagentNodeKey, DeferredSubagentRunnable],
) -> dict[str, Any]:
    return {
        "name": str(edge.binding["name"]),
        "description": str(edge.binding["description"]),
        "runnable": runnables[edge.target_key],
    }


def build_subagent_graphs(
    *,
    roots: tuple[ResolvedSubagentEdge, ...],
    nodes: dict[SubagentNodeKey, ResolvedSubagent],
    primary_id: str,
    workspace: Any,
    materialize_profile: Callable[..., dict[str, Any]],
    construct_deep_agent: Callable[..., Any],
    validate_middleware_names: Callable[..., None],
    validate_tool_names: Callable[..., None],
    report_error: Callable[..., Exception],
    agent_input_observer: Callable[[dict[str, object]], Any] | None,
    task_description_override: str | None,
) -> list[dict[str, Any]]:
    """Compile every reachable named Subagent once and bind cyclic edges."""

    runnables = {
        key: DeferredSubagentRunnable(node.name) for key, node in nodes.items()
    }
    for key, node in nodes.items():
        child = materialize_profile(
            node.references,
            node.blocks,
            filesystem_mode=node.filesystem_mode,
            scope="subagent",
            owner_id=primary_id,
            owner_name=node.name,
            workspace=workspace,
        )
        middleware = [ToolErrorBoundaryMiddleware(), *child["middleware"]]
        preset = node.blocks.get("prompt-preset")
        if preset is not None:
            middleware.insert(
                1,
                SubagentInputMiddleware(
                    agent_name=node.name,
                    preset=preset,
                    observer=agent_input_observer,
                ),
            )
        if child["tool_choice"] is not None or child["model_settings"]:
            middleware.append(
                make_model_request_settings_middleware(
                    tool_choice=child["tool_choice"],
                    model_settings=child["model_settings"],
                )
            )
        middleware.extend(child["custom_middleware"])
        middleware.append(ProviderErrorBoundaryMiddleware())
        if child["exception_retry"] is not None:
            middleware.extend(child["exception_retry"].after_provider_boundary)

        compiled_children = [
            _compiled_spec(edge, runnables) for edge in node.subagents
        ]
        try:
            if compiled_children and task_description_override is not None:
                from agent_shell.runtime.subagent_middleware import (
                    make_subagent_middleware_override,
                )

                replacement = make_subagent_middleware_override(
                    backend=child["backend"],
                    subagents=compiled_children,
                    task_description=task_description_override,
                    middleware=middleware,
                )
                if replacement is not None:
                    middleware.append(replacement)
            validate_middleware_names(
                middleware,
                owner=f"Subagent {node.name}",
            )
            middleware_names = {
                getattr(item, "name", None) for item in middleware
            }
            validate_tool_names(
                tools=child["tools"],
                middleware=middleware,
                owner=f"Subagent {node.name}",
                default_tool_names=(
                    ()
                    if "FilesystemMiddleware" in middleware_names
                    else FILESYSTEM_TOOL_NAMES
                )
                + (
                    ("task",)
                    if node.subagents and "SubAgentMiddleware" not in middleware_names
                    else ()
                ),
            )
        except AgentRuntimeError as exc:
            raise report_error(
                exc,
                scope="subagent",
                owner_id=primary_id,
                owner_name=node.name,
                path="capability_refs",
            ) from exc

        constructor: dict[str, object] = {
            "model": child["model"],
            "name": node.name,
            "middleware": middleware,
            "context_schema": AgentRequestContext,
        }
        if child["system_prompt"] is not None:
            constructor["system_prompt"] = child["system_prompt"]
        if child["tools"]:
            constructor["tools"] = child["tools"]
        if child["response_format"] is not None:
            constructor["response_format"] = child["response_format"]
        if child["backend"] is not None:
            constructor["backend"] = child["backend"]
        if child["skill_sources"]:
            constructor["skills"] = list(child["skill_sources"])
        if compiled_children:
            constructor["subagents"] = compiled_children

        graph = construct_deep_agent(
            constructor,
            model_provider=child["model_provider"],
            model_name=child["model_name"],
            scope="subagent",
            owner_id=primary_id,
            owner_name=node.name,
            subject=f"Subagent {node.name}",
            path="capability_refs",
        )
        runnables[key].bind_target(graph)

    return [_compiled_spec(edge, runnables) for edge in roots]
