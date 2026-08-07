from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.workflow.compiler import CompiledWorkflow
from agent_shell.workflow.context import WorkflowContext


def _message_text(value: object) -> str:
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, dict) and isinstance(value.get("content"), str):
        return str(value["content"])
    return str(content or value or "")


@dataclass(slots=True)
class WorkflowExecution:
    compiled: CompiledWorkflow
    input_state: dict[str, Any]
    context: WorkflowContext
    _started: bool = False
    _result_text: str = ""
    _usage: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    _finish_reason: str = "stop"
    artifact_events: list[dict[str, Any]] = field(default_factory=list)
    close: Callable[[], None] | None = None

    @property
    def usage(self) -> dict[str, int]:
        return dict(self._usage)

    @property
    def finish_reason(self) -> str:
        return self._finish_reason

    @property
    def finish_reason_source(self) -> str | None:
        return "workflow.output"

    @property
    def response_blocks(self) -> list[dict[str, Any]]:
        return []

    @property
    def media_assets(self) -> list[dict[str, Any]]:
        return []

    async def stream_text(self) -> AsyncIterator[str]:
        if self._started:
            raise RuntimeError("WorkflowExecution can only be consumed once")
        self._started = True
        try:
            result = await self.compiled.graph.ainvoke(
                self.input_state,
                context=self.context,
            )
            messages = result.get("messages", []) if isinstance(result, dict) else []
            if messages:
                self._result_text = _message_text(messages[-1])
            if self._result_text:
                yield self._result_text
        except AgentRuntimeError:
            self._finish_reason = "error"
            raise
        except Exception as exc:
            self._finish_reason = "error"
            raise AgentRuntimeError(
                "workflow.node_execution_failed",
                "The Workflow failed during node execution.",
                status_code=502,
            ) from exc
        finally:
            if self.close is not None:
                self.close()
                self.close = None

    async def run(self) -> tuple[str, dict[str, int]]:
        parts = [part async for part in self.stream_text()]
        return "".join(parts), self.usage
