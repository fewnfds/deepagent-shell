from __future__ import annotations

from typing import Annotated, Any
from typing_extensions import TypedDict
from typing_extensions import NotRequired

from deepagents import DeepAgentState
from deepagents.middleware.filesystem import FilesystemState
from langchain.agents.middleware import AgentMiddleware
from pydantic import JsonValue


def merge_shared_vars(
    current: dict[str, JsonValue] | None,
    update: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    """Merge independent public variable patches across graph branches."""

    return {**(current or {}), **(update or {})}


def merge_agent_sessions(
    current: dict[str, dict[str, Any]] | None,
    update: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Merge completed Agent invocation records by generated session ID."""

    return {**(current or {}), **(update or {})}


class WorkflowSharedState(TypedDict):
    """Shell-owned channels shared by both Workflow state modes."""

    shared_vars: NotRequired[Annotated[dict[str, JsonValue], merge_shared_vars]]
    agent_sessions: NotRequired[
        Annotated[dict[str, dict[str, Any]], merge_agent_sessions]
    ]


class AgentShellState(DeepAgentState, FilesystemState, WorkflowSharedState):
    """Official Agent state plus the Deep Agents filesystem state channel."""



class IsolatedWorkflowState(WorkflowSharedState):
    """Workflow root state whose Agent subgraphs do not share ``messages``."""

    files: FilesystemState.__annotations__["files"]


class AgentShellStateMiddleware(AgentMiddleware[AgentShellState]):
    """Expose Shell-owned shared state keys to an official synchronous Subagent."""

    state_schema = AgentShellState


__all__ = [
    "AgentShellState",
    "AgentShellStateMiddleware",
    "IsolatedWorkflowState",
    "merge_agent_sessions",
    "merge_shared_vars",
]
