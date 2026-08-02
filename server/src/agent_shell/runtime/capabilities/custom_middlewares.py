from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware

from agent_shell.registries.custom_middlewares import validate_middleware_source
from agent_shell.runtime.errors import AgentRuntimeError


def _middleware_values(value: Any, entry_name: str) -> Iterable[AgentMiddleware]:
    values = value if isinstance(value, (list, tuple)) else (value,)
    for item in values:
        if not isinstance(item, AgentMiddleware):
            raise AgentRuntimeError(
                "custom_middleware_invalid_object",
                "The selected custom Middleware entry did not produce a LangChain "
                f"Middleware object: {entry_name}.",
                status_code=422,
            )
        yield item


def materialize_custom_middlewares(
    entries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[AgentMiddleware, ...]:
    """Execute only enabled saved recipes for one Agent build."""

    materialized: list[AgentMiddleware] = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        entry_name = str(entry.get("name") or "unnamed")
        source = entry.get("source")
        if not isinstance(source, str):
            raise AgentRuntimeError(
                "custom_middleware_invalid_source",
                f"The selected custom Middleware source is invalid: {entry_name}.",
                status_code=422,
            )
        try:
            validate_middleware_source(source)
            code = compile(
                source,
                f"<agent-shell-custom-middleware:{uuid4().hex}>",
                "exec",
            )
            namespace: dict[str, Any] = {
                "__name__": f"_agent_shell_custom_middleware_{uuid4().hex}",
                "__package__": None,
            }
            exec(code, namespace, namespace)
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise AgentRuntimeError(
                "custom_middleware_execution_failed",
                f"The selected custom Middleware could not be constructed: {entry_name}.",
                status_code=422,
            ) from exc
        materialized.extend(_middleware_values(namespace.get("middleware"), entry_name))
    return tuple(materialized)
