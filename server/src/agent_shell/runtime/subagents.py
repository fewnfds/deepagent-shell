from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_shell.capability_manifest import FILESYSTEM_TOOL_NAMES
from agent_shell.runtime.agent_compilation import (
    ProfileMaterializer,
    reported_error,
    validate_middleware_names,
    validate_model_visible_tool_names,
)
from agent_shell.runtime.capabilities import DeepAgentsWorkspace
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.limits import (
    ProviderErrorBoundaryMiddleware,
    ToolErrorBoundaryMiddleware,
)
from agent_shell.runtime.model_request_settings import (
    make_model_request_settings_middleware,
)
from agent_shell.runtime.state import AgentShellStateMiddleware
from agent_shell.validation.service import (
    ResolvedSubagent,
    ResolvedSubagentEdge,
    SubagentNodeKey,
)


def build_subagent_specs(
    *,
    roots: tuple[ResolvedSubagentEdge, ...],
    nodes: dict[SubagentNodeKey, ResolvedSubagent],
    workspace: DeepAgentsWorkspace,
    materialize_profile: ProfileMaterializer,
) -> list[dict[str, Any]]:
    """Project direct children to Deep Agents' official SubAgent dictionaries."""

    return [
        _build_subagent_spec(
            nodes[edge.target_key],
            workspace=workspace,
            materialize_profile=materialize_profile,
        )
        for edge in roots
    ]


def _build_subagent_spec(
    node: ResolvedSubagent,
    *,
    workspace: DeepAgentsWorkspace,
    materialize_profile: ProfileMaterializer,
) -> dict[str, Any]:
    child = materialize_profile(
        node.references,
        node.blocks,
        filesystem_mode=node.filesystem_mode,
        scope="subagent",
        owner_id=node.key,
        owner_name=node.name,
        workspace=workspace,
    )
    middleware: list[Any] = [
        AgentShellStateMiddleware(),
        ToolErrorBoundaryMiddleware(),
        *child.middleware,
        *child.package_middleware,
    ]
    if child.tool_choice is not None or child.model_settings:
        middleware.append(
            make_model_request_settings_middleware(
                tool_choice=child.tool_choice,
                model_settings=child.model_settings,
            )
        )
    middleware.extend(child.extra_middleware)
    middleware.append(ProviderErrorBoundaryMiddleware())
    if child.exception_retry is not None:
        middleware.extend(child.exception_retry.after_provider_boundary)

    try:
        validate_middleware_names(middleware, owner=f"Subagent {node.name}")
        middleware_names = {getattr(item, "name", None) for item in middleware}
        validate_model_visible_tool_names(
            tools=child.tools,
            middleware=middleware,
            owner=f"Subagent {node.name}",
            default_tool_names=(
                ()
                if "FilesystemMiddleware" in middleware_names
                else FILESYSTEM_TOOL_NAMES
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

    spec: dict[str, Any] = {
        "name": node.name,
        "description": node.description,
        "system_prompt": child.system_prompt or "",
        "model": child.model,
        "tools": list(child.tools),
        "middleware": middleware,
    }
    if child.response_format is not None:
        spec["response_format"] = child.response_format
    if child.permissions:
        spec["permissions"] = list(child.permissions)
    return spec
