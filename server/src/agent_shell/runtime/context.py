from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping

from agent_shell.runtime.input_messages import (
    client_messages_sha,
    validate_prepared_messages,
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeContext:
    """Per-invocation context passed through the Workflow graph.

    ``messages`` is the immutable OpenAI request snapshot.  LangGraph does not
    put runtime context into the model prompt automatically; an AgentMiddleware
    hook decides how to select and write messages into that Agent's graph state.
    """

    request_id: str = ""
    messages: tuple[Mapping[str, Any], ...] = ()
    messages_sha: str = ""
    workflow: Mapping[str, Any] = field(default_factory=dict)
    prepare: Mapping[str, Any] = field(default_factory=dict)
    workflow_state: Mapping[str, Any] = field(default_factory=dict)
    workflow_node_id: str = ""
    agent_id: str = ""
    invocation_id: str = ""

    @classmethod
    def from_request(
        cls,
        raw_messages: object,
        *,
        request_id: str,
        workflow: Mapping[str, Any] | None = None,
        prepare: Mapping[str, Any] | None = None,
    ) -> "WorkflowRuntimeContext":
        messages = validate_prepared_messages(raw_messages)
        frozen_messages = tuple(
            _freeze(message) for message in deepcopy(messages)
        )
        return cls(
            request_id=request_id,
            messages=frozen_messages,
            messages_sha=client_messages_sha(messages),
            workflow=_freeze(deepcopy(dict(workflow or {}))),
            prepare=_freeze(deepcopy(dict(prepare or {}))),
        )

    def for_workflow_agent(
        self,
        workflow_state: Mapping[str, Any],
        *,
        workflow_node_id: str,
        agent_id: str,
        invocation_id: str,
    ) -> "WorkflowRuntimeContext":
        """Bind the parent State reference and canvas Agent identity to a child run."""

        return replace(
            self,
            workflow_state=workflow_state,
            workflow_node_id=workflow_node_id,
            agent_id=agent_id,
            invocation_id=invocation_id,
        )


__all__ = ["WorkflowRuntimeContext"]
