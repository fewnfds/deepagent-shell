from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from uuid import uuid4

from langchain_core.tools import BaseTool

from agent_shell.registries.custom_tools import (
    custom_tool_resource_name_issue,
    resolve_custom_tool_file,
    scan_custom_tool_file,
)
from agent_shell.runtime.errors import AgentRuntimeError


def _selected_tool_path(directory: Path, resource_name: str) -> Path:
    if custom_tool_resource_name_issue(resource_name):
        raise AgentRuntimeError(
            "tool_materialization_invalid_name",
            f"The selected custom tool name is invalid: {resource_name}.",
            status_code=422,
        )
    path = resolve_custom_tool_file(resource_name, directory)
    if path is None:
        raise AgentRuntimeError(
            "tool_materialization_not_found",
            f"The selected custom tool does not exist: {resource_name}.",
            status_code=409,
        )
    return path


def _load_selected_tool(path: Path, resource_name: str) -> BaseTool:
    try:
        metadata = scan_custom_tool_file(path)
    except ValueError as exc:
        raise AgentRuntimeError(
            "tool_materialization_invalid_source",
            f"The selected custom tool is not a valid tool module: {resource_name}.",
            status_code=422,
        ) from exc

    module_name = f"_agent_shell_custom_tool_{resource_name}_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AgentRuntimeError(
            "tool_materialization_import_failed",
            f"The selected custom tool could not be loaded: {resource_name}.",
            status_code=422,
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise AgentRuntimeError(
            "tool_materialization_import_failed",
            f"The selected custom tool could not be imported: {resource_name}.",
            status_code=422,
        ) from exc
    finally:
        sys.modules.pop(module_name, None)

    value = getattr(module, metadata["function"], None)
    if not isinstance(value, BaseTool):
        raise AgentRuntimeError(
            "tool_materialization_invalid_object",
            f"The selected custom tool did not produce a LangChain tool: {resource_name}.",
            status_code=422,
        )
    return value


def materialize_custom_tools(
    selected: list[str] | tuple[str, ...],
    *,
    directory: Path,
) -> tuple[BaseTool, ...]:
    """Import only explicitly selected custom tool modules for one Agent build."""

    tools: list[BaseTool] = []
    visible_names: dict[str, str] = {}
    for resource_name in selected:
        path = _selected_tool_path(directory, resource_name)
        tool = _load_selected_tool(path, resource_name)
        previous = visible_names.get(tool.name)
        if previous is not None:
            raise AgentRuntimeError(
                "tool_materialization_name_conflict",
                "Selected custom tools expose the same model-visible name: "
                f"{previous}, {resource_name}.",
                status_code=422,
            )
        visible_names[tool.name] = resource_name
        tools.append(tool)
    return tuple(tools)
