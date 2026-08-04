from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from agent_shell.automation.runtime import AutomationRuntime
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime


class AgentRequestContext(TypedDict):
    """Request-only data shared with compiled Subagent graphs."""

    automation_runtime: AutomationRuntime


class SubagentInputMiddleware(AgentMiddleware):
    """Build one fresh child input before the official Subagent loop starts."""

    def __init__(
        self,
        *,
        owner_id: str,
        agent_name: str,
        observer: Callable[[dict[str, object]], Any] | None = None,
    ) -> None:
        super().__init__()
        self._owner_id = owner_id
        self._agent_name = agent_name
        self._observer = observer

    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[AgentRequestContext],
    ) -> dict[str, Any] | None:
        raise RuntimeError("Automation-enabled Subagents require async invocation")

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[AgentRequestContext],
    ) -> dict[str, Any] | None:
        delegated_messages = list(state.get("messages", []))
        context = runtime.context
        if context is None:
            raise RuntimeError("The Subagent automation context is unavailable")
        rebuilt_messages = context["automation_runtime"].input_for(
            self._owner_id,
            delegated_messages,
        )
        if self._observer is not None:
            self._observer(
                {
                    "agent_type": "subagent",
                    "agent_name": self._agent_name,
                    "tool_call_id": "",
                    "message_count": len(rebuilt_messages),
                }
            )
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *rebuilt_messages,
            ]
        }
