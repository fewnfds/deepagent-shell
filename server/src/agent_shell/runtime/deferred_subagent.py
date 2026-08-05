from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig

from agent_shell.runtime.invocation import current_subagent_cause


ChildContextFactory = Callable[
    [str, Mapping[str, Any], str],
    dict[str, Any],
]


class DeferredSubagentRunnable(Runnable[dict[str, Any], dict[str, Any]]):
    """Resolve a cyclic CompiledSubAgent reference after graph construction."""

    def __init__(
        self,
        agent_name: str,
        owner_id: str,
        child_context: ChildContextFactory,
    ) -> None:
        self._agent_name = agent_name
        self._owner_id = owner_id
        self._child_context = child_context
        self._target: Runnable[dict[str, Any], dict[str, Any]] | None = None

    def bind_target(
        self,
        target: Runnable[dict[str, Any], dict[str, Any]],
    ) -> None:
        if self._target is not None:
            raise RuntimeError("Deferred Subagent runnable is already bound.")
        self._target = target

    def _resolved(self) -> Runnable[dict[str, Any], dict[str, Any]]:
        if self._target is None:
            raise RuntimeError("Deferred Subagent runnable is not bound.")
        return self._target

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
        return self._resolved().invoke(
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
        return await self._resolved().ainvoke(
            input,
            self._child_config(config),
            context=self._child_context(self._owner_id, parent, tool_call_id),
            **kwargs,
        )
