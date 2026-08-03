from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from agent_shell.runtime.prompt_preset import prepare_agent_input
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime


class AgentRequestContext(TypedDict):
    """Request-only data shared with compiled Subagent graphs."""

    client_messages: list[dict[str, str]]


class SubagentInputMiddleware(AgentMiddleware):
    """Build one fresh child input before the official Subagent loop starts."""

    def __init__(
        self,
        *,
        agent_name: str,
        preset: dict[str, Any],
        observer: Callable[[dict[str, object]], Any] | None = None,
    ) -> None:
        super().__init__()
        self._agent_name = agent_name
        self._preset = preset
        self._observer = observer

    def before_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[AgentRequestContext],
    ) -> dict[str, Any] | None:
        delegated_messages = list(state.get("messages", []))
        task = next(
            (
                message.text
                for message in reversed(delegated_messages)
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        context = runtime.context or {"client_messages": []}
        prepared = prepare_agent_input(
            context.get("client_messages", []),
            self._preset,
            variables={
                "task": task,
            },
        )
        rebuilt_messages = [*prepared.messages, *delegated_messages]
        if self._observer is not None:
            self._observer(
                {
                    "agent_type": "subagent",
                    "agent_name": self._agent_name,
                    "tool_call_id": "",
                    "message_count": len(rebuilt_messages),
                    "matched_tag_count": prepared.matched_tag_count,
                    "startup_message_count": prepared.startup_message_count,
                }
            )
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *rebuilt_messages,
            ]
        }

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[AgentRequestContext],
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)
