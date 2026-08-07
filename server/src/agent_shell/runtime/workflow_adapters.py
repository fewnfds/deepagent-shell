from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import Runnable, RunnableConfig

from agent_shell.workflow.compiler import CompiledWorkflow
from agent_shell.workflow.context import WorkflowContext


class _CompiledWorkflowSubagentRunnable(Runnable[dict[str, Any], dict[str, Any]]):
    """Translate the Deep Agents invocation context into Workflow context."""

    def __init__(self, compiled: CompiledWorkflow) -> None:
        self._compiled = compiled

    def _context(self, value: object) -> WorkflowContext:
        source = value if isinstance(value, Mapping) else {}
        invocation = source.get("agent_shell_invocation")
        details = invocation if isinstance(invocation, Mapping) else {}
        return WorkflowContext(
            request_id=str(details.get("request_id", "")),
            workflow_id=self._compiled.id,
            invocation_id=str(details.get("id", "")),
        )

    def invoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        context = self._context(kwargs.pop("context", None))
        return self._compiled.graph.invoke(
            input,
            config=config,
            context=context,
            **kwargs,
        )

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        context = self._context(kwargs.pop("context", None))
        return await self._compiled.graph.ainvoke(
            input,
            config=config,
            context=context,
            **kwargs,
        )


def as_compiled_subagent(
    compiled: CompiledWorkflow,
    *,
    description: str,
) -> dict[str, Any]:
    """Adapt one compiled Workflow to the official Deep Agents contract."""
    return {
        "name": compiled.name,
        "description": description or compiled.name,
        "runnable": _CompiledWorkflowSubagentRunnable(compiled),
    }
