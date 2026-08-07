from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_node_outputs(
    left: dict[str, dict[str, Any]] | None,
    right: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    result = dict(left or {})
    for node_id, value in (right or {}).items():
        if node_id in result:
            raise ValueError(f"Workflow node output was written twice: {node_id}")
        result[node_id] = dict(value)
    return result


class WorkflowState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    node_outputs: Annotated[dict[str, dict[str, Any]], merge_node_outputs]
    files: dict[str, Any]
