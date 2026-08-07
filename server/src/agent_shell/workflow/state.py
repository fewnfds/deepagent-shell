from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_port_values(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge addressable port channels without exposing the whole state to nodes."""

    result = dict(left or {})
    result.update(right or {})
    return result


def merge_mapping(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(left or {})
    result.update(right or {})
    return result


class WorkflowState(TypedDict, total=False):
    input_values: dict[str, Any]
    port_values: Annotated[dict[str, Any], merge_port_values]
    messages: Annotated[list[Any], add_messages]
    artifacts: Annotated[dict[str, Any], merge_mapping]
    control: Annotated[dict[str, Any], merge_mapping]
    output_values: Annotated[dict[str, Any], merge_mapping]
