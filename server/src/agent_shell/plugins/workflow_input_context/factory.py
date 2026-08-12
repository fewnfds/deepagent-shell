from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .contracts import WorkflowInputContextBlock

if TYPE_CHECKING:
    from .middleware import WorkflowInputContextMiddleware


def materialize_workflow_input_context_middleware(
    block: dict[str, Any],
    *,
    backend: Any,
) -> WorkflowInputContextMiddleware | None:
    from .middleware import WorkflowInputContextMiddleware

    configuration = WorkflowInputContextBlock.model_validate(block)
    if not configuration.enabled:
        return None
    return WorkflowInputContextMiddleware(configuration, backend=backend)


__all__ = ["materialize_workflow_input_context_middleware"]
