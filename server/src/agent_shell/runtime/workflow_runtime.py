from __future__ import annotations

import asyncio
import warnings
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.middleware_packages.runtime import MiddlewarePackageRuntime
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.media_response import MainAgentMediaResponse
from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import OutputProjector
from agent_shell.runtime.output_stream import (
    ModelCallBoundary,
    OutputEvent,
    MainAgentMediaBlock,
    V3EventNormalizer,
)
from agent_shell.storage.media_outputs import MediaOutputStore
from langgraph.errors import GraphRecursionError

EXECUTION_TIMEOUT_SECONDS = 600
GRAPH_RECURSION_LIMIT = 100


@dataclass(slots=True)
class WorkflowExecution:
    graph: Any
    input_state: dict[str, Any]
    rectifier: OutputEventRectifier
    normalizer: V3EventNormalizer
    middleware_runtime: MiddlewarePackageRuntime
    media_response: MainAgentMediaResponse
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

    @property
    def response_blocks(self) -> list[dict[str, Any]]:
        return self.media_response.structured_blocks(
            self.normalizer.last_main_agent_response
        )

    @property
    def media_assets(self) -> list[dict[str, Any]]:
        return self.media_response.assets

    async def stream_text(self) -> AsyncIterator[str]:
        if self._started:
            raise RuntimeError("WorkflowExecution can only be consumed once")
        self._started = True
        try:
            async for part in self._stream_text_inner():
                yield part
        finally:
            await self.middleware_runtime.close()

    async def _stream_text_inner(self) -> AsyncIterator[str]:

        def project_event(event: OutputEvent) -> list[str]:
            for observer in self.event_observers:
                observer(event)
            return self.rectifier.feed(event)

        def failure_output(error_code: str) -> list[str]:
            self.normalizer.abort_main_agent_messages()
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
            async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message=(
                            r"The v3 streaming protocol on Pregel is experimental\."
                        ),
                    )
                    stream_options: dict[str, Any] = {"version": "v3"}
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
                    try:
                        while next_envelope is not None:
                            timeout = self.rectifier.deadline_delay()
                            done, _pending = await asyncio.wait(
                                {next_envelope},
                                timeout=timeout,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if not done:
                                for rendered in self.rectifier.expire():
                                    if rendered:
                                        yield rendered
                                continue
                            try:
                                envelope = next_envelope.result()
                            except StopAsyncIteration:
                                next_envelope = None
                                break
                            next_envelope = asyncio.ensure_future(anext(envelopes))
                            for event in self.normalizer.feed(envelope):
                                if isinstance(event, ModelCallBoundary):
                                    projected = self.rectifier.flush()
                                elif isinstance(event, MainAgentMediaBlock):
                                    notification = await self.media_response.project(event)
                                    projected = (
                                        project_event(
                                            self.normalizer.media_notification(
                                                event, notification
                                            )
                                        )
                                        if notification is not None
                                        else []
                                    )
                                else:
                                    projected = project_event(event)
                                for rendered in projected:
                                    if rendered:
                                        yield rendered
                    finally:
                        if next_envelope is not None and not next_envelope.done():
                            next_envelope.cancel()
                            with suppress(asyncio.CancelledError):
                                await next_envelope
                    await stream.output()
                    self.normalizer.close_main_agent_messages()
                    for rendered in self.rectifier.flush():
                        if rendered:
                            yield rendered
        except asyncio.CancelledError:
            self.normalizer.abort_main_agent_messages()
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


class WorkflowRuntime:
    def __init__(
        self,
        builder: AgentBuilder,
        media_outputs: MediaOutputStore,
        diagnostics: RuntimeDiagnostics | None = None,
    ) -> None:
        self._builder = builder
        self._media_outputs = media_outputs
        self._diagnostics = diagnostics

    async def start(
        self,
        main_agent_id: str,
        raw_messages: object,
        *,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        event_observer: Callable[[OutputEvent], None] | None = None,
        request_id: str = "",
        public_model: str = "",
    ) -> WorkflowExecution:
        try:
            built = await self._builder.build(
                main_agent_id,
                raw_messages,
                model_request_interceptor=model_request_interceptor,
                model_request_observer=model_request_observer,
                model_response_observer=model_response_observer,
                request_id=request_id,
            )
        except Exception:
            await self._builder.close_failed_build()
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
        return WorkflowExecution(
            graph=built.graph,
            input_state=built.input_state,
            middleware_runtime=built.middleware_runtime,
            media_response=MainAgentMediaResponse(self._media_outputs, request_id),
            rectifier=OutputEventRectifier(OutputProjector(built.output_config)),
            normalizer=V3EventNormalizer(
                built.agent_name,
                model_response_observers=(model_response_observer,)
                if model_response_observer is not None
                else (),
            ),
            event_observers=tuple(observers),
        )
