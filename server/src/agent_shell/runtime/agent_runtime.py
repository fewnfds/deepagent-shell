from __future__ import annotations

import asyncio
import warnings
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from agent_shell.runtime.agent_builder import AgentBuilder, BuiltAgent
from agent_shell.middleware_packages.runtime import MiddlewarePackageRuntime
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.media_response import MainAgentMediaResponse
from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import OutputProjector, WorkflowOutputProjector
from agent_shell.runtime.output_stream import (
    ModelCallBoundary,
    OutputEvent,
    MainAgentMediaBlock,
    V3EventNormalizer,
)
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1
from langgraph.errors import GraphRecursionError

EXECUTION_TIMEOUT_SECONDS = 600
GRAPH_RECURSION_LIMIT = 100


@dataclass(slots=True)
class AgentExecution:
    graph: Any
    input_state: dict[str, Any]
    rectifier: OutputEventRectifier
    normalizer: V3EventNormalizer
    middleware_runtime: MiddlewarePackageRuntime
    media_response: MainAgentMediaResponse
    event_observers: tuple[Callable[[OutputEvent], None], ...] = ()
    final_state: dict[str, Any] | None = None
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
            raise RuntimeError("AgentExecution can only be consumed once")
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
                    output = await stream.output()
                    self.final_state = dict(output) if isinstance(output, Mapping) else None
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


class AgentRuntime:
    def __init__(
        self,
        builder: AgentBuilder,
        media_outputs: MediaOutputStore,
        diagnostics: RuntimeDiagnostics | None = None,
    ) -> None:
        self._builder = builder
        self._media_outputs = media_outputs
        self._diagnostics = diagnostics

    async def build_agent(
        self,
        main_agent_id: str,
        raw_messages: object,
        *,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        request_id: str = "",
        workflow_filesystem_id: str | None = None,
    ) -> BuiltAgent:
        try:
            return await self._builder.build(
                main_agent_id,
                raw_messages,
                model_request_interceptor=model_request_interceptor,
                model_request_observer=model_request_observer,
                model_response_observer=model_response_observer,
                request_id=request_id,
                workflow_filesystem_id=workflow_filesystem_id,
            )
        except Exception:
            await self._builder.close_failed_build()
            raise

    def _execution(
        self,
        built: BuiltAgent,
        *,
        graph: Any | None = None,
        workflow_node_id: str = "",
        event_observer: Callable[[OutputEvent], None] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        request_id: str = "",
        public_model: str = "",
    ) -> AgentExecution:
        observers = []
        if event_observer is not None:
            observers.append(event_observer)
        if self._diagnostics is not None:
            observers.append(
                lambda event: self._diagnostics.runtime_event(
                    event, request_id=request_id, model=public_model
                )
            )
        if workflow_node_id:
            from agent_shell.workflow.events import WorkflowEventSourceV1

            workflow_sources = {
                workflow_node_id: WorkflowEventSourceV1(
                    source_type="agent",
                    workflow_node_id=workflow_node_id,
                    agent_profile_id=built.agent_id,
                )
            }
            projector = WorkflowOutputProjector(
                {workflow_node_id: built.output_config}
            )
        else:
            workflow_sources = None
            projector = OutputProjector(built.output_config)
        return AgentExecution(
            graph=graph if graph is not None else built.graph,
            input_state=built.input_state,
            middleware_runtime=built.middleware_runtime,
            media_response=MainAgentMediaResponse(self._media_outputs, request_id),
            rectifier=OutputEventRectifier(projector),
            normalizer=V3EventNormalizer(
                built.agent_name,
                model_response_observers=(model_response_observer,)
                if model_response_observer is not None
                else (),
                workflow_sources=workflow_sources,
                subagent_profile_ids=built.subagent_profile_ids,
            ),
            event_observers=tuple(observers),
        )

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
        workflow_filesystem_id: str | None = None,
    ) -> AgentExecution:
        built = await self.build_agent(
            main_agent_id,
            raw_messages,
            model_request_interceptor=model_request_interceptor,
            model_request_observer=model_request_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            workflow_filesystem_id=workflow_filesystem_id,
        )
        return self._execution(
            built,
            event_observer=event_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            public_model=public_model,
        )

    async def start_workflow(
        self,
        document: WorkflowGraphDocumentV1,
        raw_messages: object,
        *,
        workflow_filesystem_id: str,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        event_observer: Callable[[OutputEvent], None] | None = None,
        request_id: str = "",
        public_model: str = "",
    ) -> AgentExecution:
        from agent_shell.workflow.catalog import AgentNodeConfig
        from agent_shell.workflow.compiler import compile_workflow

        agent_nodes = [
            node for node in document.definition.nodes if node.type == "agent"
        ]
        if len(agent_nodes) != 1:
            raise AgentRuntimeError(
                "workflow.agent_count_unsupported",
                "The first Workflow runtime requires exactly one Agent node.",
                status_code=422,
            )
        agent_node = agent_nodes[0]
        main_agent_id = str(
            AgentNodeConfig.model_validate(agent_node.config).main_agent_id
        )
        built = await self.build_agent(
            main_agent_id,
            raw_messages,
            model_request_interceptor=model_request_interceptor,
            model_request_observer=model_request_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            workflow_filesystem_id=workflow_filesystem_id,
        )
        try:
            graph = compile_workflow(
                document,
                agent_graphs={agent_node.id: built.graph},
            )
        except Exception:
            await built.middleware_runtime.close()
            raise
        return self._execution(
            built,
            graph=graph,
            workflow_node_id=agent_node.id,
            event_observer=event_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            public_model=public_model,
        )
