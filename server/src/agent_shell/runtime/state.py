from __future__ import annotations

from typing import Annotated
from typing_extensions import NotRequired

from deepagents import DeepAgentState
from pydantic import JsonValue


def merge_shared_vars(
    current: dict[str, JsonValue] | None,
    update: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    """Merge independent public variable patches across graph branches."""

    return {**(current or {}), **(update or {})}


class AgentShellState(DeepAgentState):
    """Checkpointed public state shared by Main Agent and direct Subagents."""

    shared_vars: NotRequired[Annotated[dict[str, JsonValue], merge_shared_vars]]


__all__ = ["AgentShellState", "merge_shared_vars"]
