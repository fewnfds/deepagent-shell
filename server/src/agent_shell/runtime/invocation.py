from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command


InvocationData = Mapping[str, Any]
SubagentCause = tuple[InvocationData, str]

_SUBAGENT_CAUSE: ContextVar[SubagentCause | None] = ContextVar(
    "agent_shell_subagent_cause", default=None
)


def current_subagent_cause() -> SubagentCause | None:
    return _SUBAGENT_CAUSE.get()


def _context_from_runtime(runtime: object, context_key: str | None = None) -> Mapping[str, Any]:
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        raise RuntimeError("The Agent invocation context is unavailable")
    contexts = context.get("agent_contexts")
    if context_key is not None and isinstance(contexts, Mapping):
        selected = contexts.get(context_key)
        if not isinstance(selected, Mapping):
            raise RuntimeError("The Graph Agent context is unavailable")
        return selected
    return context


def _invocation_from_runtime(runtime: object, context_key: str | None = None) -> InvocationData:
    context = _context_from_runtime(runtime, context_key)
    invocation = context.get("agent_shell_invocation")
    if not isinstance(invocation, Mapping):
        raise RuntimeError("The Agent invocation identity is unavailable")
    return invocation


class AgentInvocationMiddleware(AgentMiddleware):
    """Observe Agent starts and propagate task-call cause to child runnables."""

    def __init__(
        self,
        *,
        agent_type: str,
        agent_name: str,
        observer: Callable[[dict[str, object]], Any] | None = None,
        context_key: str | None = None,
    ) -> None:
        super().__init__()
        self._agent_type = agent_type
        self._agent_name = agent_name
        self._observer = observer
        self._context_key = context_key

    def _observe(self, state: dict[str, Any], runtime: object) -> None:
        if self._observer is None:
            return
        invocation = _invocation_from_runtime(runtime, self._context_key)
        messages = state.get("messages", [])
        self._observer(
            {
                "agent_type": self._agent_type,
                "agent_name": self._agent_name,
                "owner_id": str(invocation["agent_id"]),
                "invocation_id": str(invocation["id"]),
                "parent_invocation_id": str(invocation["parent_id"]),
                "tool_call_id": str(invocation["cause_tool_call_id"]),
                "message_count": len(messages) if isinstance(messages, list) else 0,
            }
        )

    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        self._observe(state, runtime)

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> None:
        self._observe(state, runtime)

    @staticmethod
    def _is_task(request: ToolCallRequest) -> bool:
        return str(request.tool_call.get("name") or "") == "task"

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if not self._is_task(request):
            return handler(request)
        invocation = _invocation_from_runtime(request.runtime, self._context_key)
        tool_call_id = str(request.runtime.tool_call_id or "")
        if not tool_call_id:
            raise RuntimeError("The Subagent tool call identity is unavailable")
        token = _SUBAGENT_CAUSE.set((invocation, tool_call_id))
        try:
            return handler(request)
        finally:
            _SUBAGENT_CAUSE.reset(token)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[
            [ToolCallRequest], Awaitable[ToolMessage | Command[Any]]
        ],
    ) -> ToolMessage | Command[Any]:
        if not self._is_task(request):
            return await handler(request)
        invocation = _invocation_from_runtime(request.runtime, self._context_key)
        tool_call_id = str(request.runtime.tool_call_id or "")
        if not tool_call_id:
            raise RuntimeError("The Subagent tool call identity is unavailable")
        token = _SUBAGENT_CAUSE.set((invocation, tool_call_id))
        try:
            return await handler(request)
        finally:
            _SUBAGENT_CAUSE.reset(token)


__all__ = [
    "AgentInvocationMiddleware",
    "InvocationData",
    "current_subagent_cause",
]
