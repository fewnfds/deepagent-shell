from __future__ import annotations

from typing import Any

from .contracts import SessionRecorderBlock
from .middleware import SessionRecorderMiddleware


def materialize_session_recorder_middleware(
    block: dict[str, Any],
    *,
    backend: Any,
    agent_scope: str,
    agent_id: str,
    agent_name: str,
    workflow_node_id: str | None,
) -> SessionRecorderMiddleware | None:
    configuration = SessionRecorderBlock.model_validate(block)
    if not configuration.enabled:
        return None
    return SessionRecorderMiddleware(
        configuration,
        backend=backend,
        agent_scope=agent_scope,
        agent_id=agent_id,
        agent_name=agent_name,
        workflow_node_id=workflow_node_id,
    )


__all__ = ["materialize_session_recorder_middleware"]
