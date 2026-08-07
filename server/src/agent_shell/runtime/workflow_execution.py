from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import asyncio
from typing import Any

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
    thread_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    _started: bool = False
    _result_text: str = ""
    _usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    _finish_reason: str = "stop"
    artifact_events: list[dict[str, Any]] = field(default_factory=list)
    close: Any = None

    @property
    def usage(self) -> dict[str, int]:
        return dict(self._usage)

    @property
    def finish_reason(self) -> str:
        return self._finish_reason

    @property
    def finish_reason_source(self) -> str | None:
        return "graph"

    @property
    def response_blocks(self) -> list[dict[str, Any]]:
        return []

    @property
    def media_assets(self) -> list[dict[str, Any]]:
        return []

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        if self._started:
            raise RuntimeError("WorkflowExecution can only be consumed once")
        self._started = True
        terminal: dict[str, Any] = {"status": "failed", "error_code": "workflow_failed"}
        agents_started = self.compiled.start is not None
        try:
            if self.compiled.start is not None:
                await self.compiled.start()
            config = dict(self.config)
            config.setdefault("recursion_limit", self.compiled.definition.recursion_limit)
            if self.thread_id:
                config.setdefault("configurable", {})["thread_id"] = self.thread_id
            stream_kwargs: dict[str, Any] = {
                "context": self.context,
                "config": config,
                "stream_mode": ["updates", "values"],
                "version": "v2",
                "subgraphs": True,
            }
            if getattr(self.compiled.graph, "checkpointer", None) is not None:
                stream_kwargs["durability"] = "sync"
            async for event in self.compiled.graph.astream(
                self.input_state,
                **stream_kwargs,
            ):
                if isinstance(event, dict):
                    yield event
                    if event.get("type") == "values" and isinstance(event.get("data"), dict):
                        messages = event["data"].get("messages") or []
                        if messages:
                            self._result_text = _message_text(messages[-1])
            terminal = {"status": "completed", "finish_reason": self._finish_reason}
        except asyncio.CancelledError:
            self._finish_reason = "cancelled"
            terminal = {"status": "cancelled", "error_code": "request_cancelled"}
            raise
        except AgentRuntimeError as exc:
            self._finish_reason = "error"
            terminal = {"status": "failed", "error_code": exc.code}
            raise
        except Exception as exc:
            self._finish_reason = "error"
            terminal = {"status": "failed", "error_code": "workflow.node_execution_failed"}
            raise AgentRuntimeError("workflow.node_execution_failed", "The Graph failed during node execution.", status_code=502) from exc
        finally:
            try:
                if self.compiled.finish is not None and agents_started:
                    await self.compiled.finish(terminal)
            finally:
                try:
                    if self.compiled.cleanup is not None:
                        self.compiled.cleanup()
                finally:
                    if self.close is not None:
                        self.close()
                        self.close = None

    async def stream_text(self) -> AsyncIterator[str]:
        async for event in self.stream_events():
            if event.get("type") != "updates":
                continue
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            for update in data.values():
                if not isinstance(update, dict):
                    continue
                messages = update.get("messages") or []
                if messages:
                    text = _message_text(messages[-1])
                    if text:
                        self._result_text = text
                        yield text
        if self._result_text:
            return

    async def run(self) -> tuple[str, dict[str, int]]:
        parts = [part async for part in self.stream_text()]
        return "".join(parts) if parts else self._result_text, self.usage
