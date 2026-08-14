from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .contracts import WorkflowInputContextBlock

if TYPE_CHECKING:
    from .middleware import WorkflowInputContextMiddleware


def materialize_workflow_input_context_middleware(
    block: dict[str, Any],
    *,
    backend: Any,
    agent_scope: str,
) -> WorkflowInputContextMiddleware:
    from .middleware import WorkflowInputContextMiddleware

    configuration = WorkflowInputContextBlock.model_validate(block)
    return WorkflowInputContextMiddleware(
        configuration,
        backend=backend,
        agent_scope=agent_scope,
    )


__all__ = ["materialize_workflow_input_context_middleware"]
