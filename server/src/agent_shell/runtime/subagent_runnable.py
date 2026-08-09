from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig

from agent_shell.runtime.invocation import current_subagent_cause


ChildContextFactory = Callable[
    [str, Mapping[str, Any], str],
    dict[str, Any],
]


class SubagentInvocationRunnable(Runnable[dict[str, Any], dict[str, Any]]):
    """Attach one Shell child invocation context to a compiled Subagent graph."""

    def __init__(
        self,
        agent_name: str,
        owner_id: str,
        target: Runnable[dict[str, Any], dict[str, Any]],
        child_context: ChildContextFactory,
    ) -> None:
        self._agent_name = agent_name
        self._owner_id = owner_id
        self._target = target
        self._child_context = child_context

    def _child_config(self, config: RunnableConfig | None) -> RunnableConfig:
        child_config = dict(config or {})
        child_config["metadata"] = {
            **dict(child_config.get("metadata") or {}),
            "lc_agent_name": self._agent_name,
        }
        child_config["run_name"] = self._agent_name
        return child_config

    def invoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        cause = current_subagent_cause()
        if cause is None:
            raise RuntimeError("The Subagent invocation cause is unavailable")
        parent, tool_call_id = cause
        return self._target.invoke(
            input,
            self._child_config(config),
            context=self._child_context(self._owner_id, parent, tool_call_id),
            **kwargs,
        )

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        cause = current_subagent_cause()
        if cause is None:
            raise RuntimeError("The Subagent invocation cause is unavailable")
        parent, tool_call_id = cause
        return await self._target.ainvoke(
            input,
            self._child_config(config),
            context=self._child_context(self._owner_id, parent, tool_call_id),
            **kwargs,
        )
