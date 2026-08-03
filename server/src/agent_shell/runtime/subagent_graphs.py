from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_shell.capability_manifest import FILESYSTEM_TOOL_NAMES
from agent_shell.runtime.agent_compilation import (
    ProfileMaterializer,
    construct_deep_agent,
    reported_error,
    validate_middleware_names,
    validate_model_visible_tool_names,
)
from agent_shell.runtime.capabilities import DeepAgentsWorkspace
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
    nodes: dict[SubagentNodeKey, ResolvedSubagent],
) -> dict[str, Any]:
    node = nodes[edge.target_key]
    return {
        "name": node.name,
        "description": node.description,
        "runnable": runnables[edge.target_key],
    }


class SubagentGraphCompiler:
    """Compile reachable named Subagents against one request-local workspace."""

    def __init__(
        self,
        *,
        workspace: DeepAgentsWorkspace,
        materialize_profile: ProfileMaterializer,
        agent_input_observer: Callable[[dict[str, object]], Any] | None,
    ) -> None:
        self._workspace = workspace
        self._materialize_profile = materialize_profile
        self._agent_input_observer = agent_input_observer

    def compile(
        self,
        *,
        roots: tuple[ResolvedSubagentEdge, ...],
        nodes: dict[SubagentNodeKey, ResolvedSubagent],
    ) -> list[dict[str, Any]]:
        runnables = {
            key: DeferredSubagentRunnable(node.name) for key, node in nodes.items()
        }
        for key, node in nodes.items():
            self._compile_node(node, runnables[key], runnables, nodes)
        return [_compiled_spec(edge, runnables, nodes) for edge in roots]

    def _compile_node(
        self,
        node: ResolvedSubagent,
        runnable: DeferredSubagentRunnable,
        runnables: dict[SubagentNodeKey, DeferredSubagentRunnable],
        nodes: dict[SubagentNodeKey, ResolvedSubagent],
    ) -> None:
        child = self._materialize_profile(
            node.references,
            node.blocks,
            filesystem_mode=node.filesystem_mode,
            scope="subagent",
            owner_id=node.key,
            owner_name=node.name,
            workspace=self._workspace,
        )
        middleware = [ToolErrorBoundaryMiddleware(), *child.middleware]
        preset = node.blocks.get("prompt-preset")
        if preset is not None:
            middleware.insert(
                1,
                SubagentInputMiddleware(
                    agent_name=node.name,
                    preset=preset,
                    observer=self._agent_input_observer,
                ),
            )
        if child.tool_choice is not None or child.model_settings:
            middleware.append(
                make_model_request_settings_middleware(
                    tool_choice=child.tool_choice,
                    model_settings=child.model_settings,
                )
            )
        middleware.extend(child.custom_middleware)
        middleware.append(ProviderErrorBoundaryMiddleware())
        if child.exception_retry is not None:
            middleware.extend(child.exception_retry.after_provider_boundary)

        compiled_children = [
            _compiled_spec(edge, runnables, nodes) for edge in node.subagents
        ]
        delegation = node.blocks.get("subagent")
        task_description_override = (
            delegation.get("task_description_override")
            if delegation is not None
            else None
        )
        try:
            if compiled_children and task_description_override is not None:
                from agent_shell.runtime.subagent_middleware import (
                    make_subagent_middleware_override,
                )

                replacement = make_subagent_middleware_override(
                    backend=child.backend,
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
            validate_model_visible_tool_names(
                tools=child.tools,
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
            raise reported_error(
                exc,
                scope="subagent",
                owner_id=node.key,
                owner_name=node.name,
                path="capability_refs",
            ) from exc

        constructor: dict[str, object] = {
            "model": child.model,
            "name": node.name,
            "middleware": middleware,
            "context_schema": AgentRequestContext,
        }
        if child.system_prompt is not None:
            constructor["system_prompt"] = child.system_prompt
        if compiled_children and delegation is not None:
            delegation_instruction = delegation.get("instruction_override")
            if delegation_instruction is not None:
                existing_prompt = str(constructor.get("system_prompt") or "")
                constructor["system_prompt"] = "\n\n".join(
                    part
                    for part in (existing_prompt, delegation_instruction)
                    if part
                )
        if child.tools:
            constructor["tools"] = list(child.tools)
        if child.response_format is not None:
            constructor["response_format"] = child.response_format
        if child.backend is not None:
            constructor["backend"] = child.backend
        if child.skill_sources:
            constructor["skills"] = list(child.skill_sources)
        if compiled_children:
            constructor["subagents"] = compiled_children

        graph = construct_deep_agent(
            constructor,
            model_provider=child.model_provider,
            model_name=child.model_name,
            scope="subagent",
            owner_id=node.key,
            owner_name=node.name,
            subject=f"Subagent {node.name}",
            path="capability_refs",
        )
        runnable.bind_target(graph)
