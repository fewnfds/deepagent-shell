from __future__ import annotations

import asyncio
import warnings
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.automation.runtime import AutomationRuntime
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import OutputProjector
from agent_shell.runtime.output_stream import (
    ModelCallBoundary,
    OutputEvent,
    V3EventNormalizer,
)
from langgraph.errors import GraphRecursionError

EXECUTION_TIMEOUT_SECONDS = 600
GRAPH_RECURSION_LIMIT = 100


@dataclass(slots=True)
class AgentExecution:
    graph: Any
    input_state: dict[str, Any]
    rectifier: OutputEventRectifier
    normalizer: V3EventNormalizer
    automation: AutomationRuntime
    context: dict[str, Any] = field(default_factory=dict)
    event_observers: tuple[Callable[[OutputEvent], None], ...] = ()
    _started: bool = False

    @property
    def usage(self) -> dict[str, int]:
        return dict(self.normalizer.usage)

    @property
    def finish_reason(self) -> str:
        return self.normalizer.finish_reason

    @property
    def finish_reason_source(self) -> str | None:
        return self.normalizer.finish_reason_source

    async def stream_text(self) -> AsyncIterator[str]:
        if self._started:
            raise RuntimeError("AgentExecution can only be consumed once")
        self._started = True
        terminal: dict[str, Any] = {
            "status": "failed",
            "error_code": "execution_aborted",
        }
        await self.automation.start()
        try:
            async for part in self._stream_text_inner():
                yield part
            terminal = {
                "status": "completed",
                "finish_reason": self.normalizer.finish_reason,
            }
        except asyncio.CancelledError:
            terminal = {"status": "cancelled", "error_code": "request_cancelled"}
            raise
        except AgentRuntimeError as exc:
            terminal = {"status": "failed", "error_code": exc.code}
            raise
        except Exception:
            terminal = {"status": "failed", "error_code": "agent_execution_failed"}
            raise
        finally:
            await self.automation.finish(terminal)

    async def _stream_text_inner(self) -> AsyncIterator[str]:

        def project_event(event: OutputEvent) -> list[str]:
            for observer in self.event_observers:
                observer(event)
            return self.rectifier.feed(event)

        def failure_output(error_code: str) -> list[str]:
            self.normalizer.abort_primary_messages()
            parts = self.rectifier.abort()
            parts.extend(
                project_event(
                    self.normalizer.lifecycle(
                        "error",
                        status="failed",
                        finish_reason="error",
                        error_code=error_code,
                    )
                )
            )
            return parts

        for rendered in project_event(
            self.normalizer.lifecycle("start", status="running")
        ):
            if rendered:
                yield rendered

        try:
            if self.automation.graph_stop_requested:
                raise self.automation.graph_stop_error()
            async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=(
                            r"The v3 streaming protocol on Pregel is experimental\."
                        ),
                    )
                    stream_options: dict[str, Any] = {"version": "v3"}
                    if self.context:
                        stream_options["context"] = self.context
                    stream = await self.graph.astream_events(
                        self.input_state,
                        config={"recursion_limit": GRAPH_RECURSION_LIMIT},
                        **stream_options,
                    )
                # The v3 run stream owns the graph iterator. Its async context
                # manager aborts in-flight provider/tool work when an OpenAI
                # streaming client disconnects and this generator is cancelled.
                async with stream:
                    envelopes = aiter(stream)
                    next_envelope: asyncio.Future[object] | None = (
                        asyncio.ensure_future(anext(envelopes))
                    )
                    graph_stop = asyncio.create_task(
                        self.automation.wait_for_graph_stop()
                    )
                    try:
                        while next_envelope is not None:
                            timeout = self.rectifier.deadline_delay()
                            done, _pending = await asyncio.wait(
                                {next_envelope, graph_stop},
                                timeout=timeout,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if not done:
                                for rendered in self.rectifier.expire():
                                    if rendered:
                                        yield rendered
                                continue
                            if graph_stop in done:
                                raise self.automation.graph_stop_error()
                            try:
                                envelope = next_envelope.result()
                            except StopAsyncIteration:
                                next_envelope = None
                                break
                            next_envelope = asyncio.ensure_future(anext(envelopes))
                            for event in self.normalizer.feed(envelope):
                                projected = (
                                    self.rectifier.flush()
                                    if isinstance(event, ModelCallBoundary)
                                    else project_event(event)
                                )
                                for rendered in projected:
                                    if rendered:
                                        yield rendered
                    finally:
                        if not graph_stop.done():
                            graph_stop.cancel()
                            with suppress(asyncio.CancelledError):
                                await graph_stop
                        if next_envelope is not None and not next_envelope.done():
                            next_envelope.cancel()
                            with suppress(asyncio.CancelledError):
                                await next_envelope
                    await stream.output()
                    self.normalizer.close_primary_messages()
                    for rendered in self.rectifier.flush():
                        if rendered:
                            yield rendered
        except asyncio.CancelledError:
            self.normalizer.abort_primary_messages()
            self.rectifier.discard()
            raise
        except TimeoutError as exc:
            error = AgentRuntimeError(
                "execution_timeout",
                "The Agent execution exceeded the runtime time limit.",
                status_code=504,
            )
            for rendered in failure_output(error.code):
                yield rendered
            raise error from exc
        except AgentRuntimeError as exc:
            for rendered in failure_output(exc.code):
                yield rendered
            raise
        except Exception as exc:
            if isinstance(exc, GraphRecursionError):
                error = AgentRuntimeError(
                    "execution_step_limit",
                    "The Agent exceeded the runtime step limit.",
                    status_code=508,
                )
            else:
                error = AgentRuntimeError(
                    "agent_execution_failed",
                    "The Agent failed during graph execution.",
                    status_code=502,
                )
            for rendered in failure_output(error.code):
                yield rendered
            raise error from exc
        for rendered in project_event(
            self.normalizer.lifecycle(
                "end", status="completed", finish_reason=self.normalizer.finish_reason
            )
        ):
            if rendered:
                yield rendered

    async def run(self) -> tuple[str, dict[str, int]]:
        parts = [part async for part in self.stream_text()]
        return "".join(parts), self.usage


class AgentRuntime:
    def __init__(
        self, builder: AgentBuilder, diagnostics: RuntimeDiagnostics | None = None
    ) -> None:
        self._builder = builder
        self._diagnostics = diagnostics

    async def start(
        self,
        primary_id: str,
        raw_messages: object,
        *,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        agent_input_observer: Callable[[dict[str, object]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        event_observer: Callable[[OutputEvent], None] | None = None,
        request_id: str = "",
        public_model: str = "",
    ) -> AgentExecution:
        try:
            built = await self._builder.build(
                primary_id,
                raw_messages,
                model_request_interceptor=model_request_interceptor,
                model_request_observer=model_request_observer,
                agent_input_observer=agent_input_observer,
                model_response_observer=model_response_observer,
                request_id=request_id,
            )
        except Exception:
            await self._builder.finish_failed_build()
            raise
        observers = []
        if event_observer is not None:
            observers.append(event_observer)
        if self._diagnostics is not None:
            observers.append(
                lambda event: self._diagnostics.runtime_event(
                    event, request_id=request_id, model=public_model
                )
            )
        return AgentExecution(
            graph=built.graph,
            input_state=built.input_state,
            context=built.context,
            automation=built.automation,
            rectifier=OutputEventRectifier(OutputProjector(built.output_config)),
            normalizer=V3EventNormalizer(
                built.agent_name,
                model_response_observers=(model_response_observer,)
                if model_response_observer is not None
                else (),
            ),
            event_observers=tuple(observers),
        )
