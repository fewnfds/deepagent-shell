from __future__ import annotations

from typing import Annotated
from typing_extensions import TypedDict
from typing_extensions import NotRequired

from deepagents import DeepAgentState
from deepagents.middleware.filesystem import FilesystemState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AnyMessage
from pydantic import JsonValue


def merge_shared_vars(
    current: dict[str, JsonValue] | None,
    update: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    """Merge independent public variable patches across graph branches."""

    return {**(current or {}), **(update or {})}


class WorkflowTaskContext(TypedDict):
    dispatcher_node_id: str
    dispatcher_invocation_id: str
    task_id: str
    dispatch_key: str
    payload: dict[str, JsonValue]


class AgentInvocationRecord(TypedDict):
    invocation_id: str
    workflow_id: str
    workflow_node_id: str
    agent_id: str
    invoked_at: float
    messages: list[AnyMessage]
    workflow_task: NotRequired[WorkflowTaskContext]


def merge_agent_invocations(
    current: dict[str, AgentInvocationRecord] | None,
    update: dict[str, AgentInvocationRecord] | None,
) -> dict[str, AgentInvocationRecord]:
    """Merge independently identified Agent invocations across graph branches."""

    return {**(current or {}), **(update or {})}


class WorkflowState(TypedDict):
    """Workflow-owned channels; Agent conversations are provenance records."""

    shared_vars: NotRequired[Annotated[dict[str, JsonValue], merge_shared_vars]]
    agent_invocations: NotRequired[
        Annotated[
            dict[str, AgentInvocationRecord],
            merge_agent_invocations,
        ]
    ]
    files: FilesystemState.__annotations__["files"]


class WorkflowNodeInputState(WorkflowState):
    """Workflow node input plus an optional private Send payload."""

    workflow_task: NotRequired[WorkflowTaskContext]


class AgentShellState(DeepAgentState, FilesystemState):
    """Private Agent state plus Shell-owned variables mapped by its wrapper."""

    shared_vars: NotRequired[Annotated[dict[str, JsonValue], merge_shared_vars]]
    workflow_task: NotRequired[WorkflowTaskContext]


class AgentShellStateMiddleware(AgentMiddleware[AgentShellState]):
    """Expose Shell-owned shared state keys to an official synchronous Subagent."""

    state_schema = AgentShellState


__all__ = [
    "AgentInvocationRecord",
    "AgentShellState",
    "AgentShellStateMiddleware",
    "WorkflowState",
    "WorkflowNodeInputState",
    "WorkflowTaskContext",
    "merge_agent_invocations",
    "merge_shared_vars",
]
