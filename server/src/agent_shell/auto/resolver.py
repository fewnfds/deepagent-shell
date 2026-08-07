from __future__ import annotations

import inspect
from typing import Any

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.root_target import validate_public_root_id


async def resolve_auto_source(source: str, messages: object) -> dict[str, str]:
    namespace: dict[str, Any] = {"__name__": "agent_shell.auto_script"}
    try:
        exec(compile(source, "<auto-root>", "exec"), namespace, namespace)
    except Exception as exc:
        raise AgentRuntimeError(
            "auto.script_compile_failed",
            "The Auto routing script could not be loaded.",
            status_code=422,
        ) from exc
    route = namespace.get("route")
    if not callable(route):
        raise AgentRuntimeError(
            "auto.route_missing",
            "The Auto routing script must define route(messages).",
            status_code=422,
        )
    try:
        result = route(messages)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        raise AgentRuntimeError(
            "auto.route_failed",
            "The Auto routing script failed.",
            status_code=422,
        ) from exc
    if isinstance(result, str):
        kind = "workflow" if result.startswith("workflow-") else "agent"
        public_id = result
    elif isinstance(result, dict):
        kind = result.get("kind")
        public_id = result.get("public_id")
    else:
        kind = None
        public_id = None
    if kind not in {"agent", "workflow"} or not isinstance(public_id, str):
        raise AgentRuntimeError(
            "auto.route_result_invalid",
            "The Auto routing script must select an agent or workflow public id.",
            status_code=422,
        )
    try:
        validate_public_root_id(public_id, kind=kind)
    except ValueError as exc:
        raise AgentRuntimeError(
            "auto.route_result_invalid",
            "The Auto routing script returned an invalid public id.",
            status_code=422,
        ) from exc
    return {"kind": kind, "public_id": public_id}
