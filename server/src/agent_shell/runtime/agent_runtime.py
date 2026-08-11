from __future__ import annotations

import asyncio
import warnings
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from agent_shell.runtime.agent_builder import AgentBuilder, BuiltAgent
from agent_shell.runtime.capabilities import DeepAgentsWorkspace
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.middleware_packages.runtime import MiddlewarePackageRuntime
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
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
from agent_shell.runtime.stream_transformers import RawCustomEventTransformer
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.runtime.workflow_debug import WorkflowDebugRun, WorkflowDebugService
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
    middleware_runtimes: tuple[MiddlewarePackageRuntime, ...] = ()
    event_observers: tuple[Callable[[OutputEvent], None], ...] = ()
    context: WorkflowRuntimeContext | None = None
    run_config: dict[str, Any] | None = None
    durability: str | None = None
    debug_run: WorkflowDebugRun | None = None
    runtime_diagnostics: RuntimeDiagnostics | None = None
    request_id: str = ""
    public_model: str = ""
    agent_name: str = ""
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
            runtimes = (self.middleware_runtime, *self.middleware_runtimes)
            for runtime in runtimes:
                await runtime.close()

    async def _stream_text_inner(self) -> AsyncIterator[str]:

        async def finish_debug(
            status: str,
            *,
            error_code: str = "",
            error: BaseException | None = None,
        ) -> None:
            if self.debug_run is None:
                return
            try:
                await self.debug_run.finish(
                    status,
                    error_code=error_code,
                    error=error,
                )
            except Exception as exc:
                if self.runtime_diagnostics is not None:
                    self.runtime_diagnostics.observation_error(
                        exc,
                        request_id=self.request_id,
                        model=self.public_model,
                        agent_name=self.agent_name,
                        code="workflow_debug_record_failed",
                    )

        def record_runtime_error(exc: BaseException, code: str) -> None:
            if self.runtime_diagnostics is not None:
                self.runtime_diagnostics.runtime_error(
                    exc,
                    request_id=self.request_id,
                    model=self.public_model,
                    agent_name=self.agent_name,
                    code=code,
                )

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
                    config: dict[str, Any] = {
                        "recursion_limit": GRAPH_RECURSION_LIMIT,
                        **(self.run_config or {}),
                    }
                    stream_kwargs: dict[str, Any] = {
                        "config": config,
                        "version": "v3",
                        "transformers": (RawCustomEventTransformer,),
                    }
                    if self.durability is not None:
                        stream_kwargs["durability"] = self.durability
                    if self.context is not None:
                        stream_kwargs["context"] = self.context
                    stream = await self.graph.astream_events(
                        self.input_state,
                        **stream_kwargs,
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
                                    if event.source_key and event.cycle_key:
                                        projected = self.rectifier.flush_cycle(
                                            event.source_key, event.cycle_key
                                        )
                                    elif event.source_key:
                                        projected = self.rectifier.flush_source(
                                            event.source_key
                                        )
                                    else:
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
            await finish_debug("cancelled", error_code="request_cancelled")
            raise
        except TimeoutError as exc:
            error = AgentRuntimeError(
                "execution_timeout",
                "The Agent execution exceeded the runtime time limit.",
                status_code=504,
            )
            for rendered in failure_output(error.code):
                yield rendered
            record_runtime_error(error, error.code)
            await finish_debug("failed", error_code=error.code, error=error)
            raise error from exc
        except AgentRuntimeError as exc:
            for rendered in failure_output(exc.code):
                yield rendered
            record_runtime_error(exc, exc.code)
            await finish_debug("failed", error_code=exc.code, error=exc)
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
            record_runtime_error(error, error.code)
            await finish_debug("failed", error_code=error.code, error=error)
            raise error from exc
        await finish_debug("completed")
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
        *,
        workflow_debug: WorkflowDebugService | None = None,
        runtime_diagnostics: RuntimeDiagnostics | None = None,
    ) -> None:
        self._builder = builder
        self._media_outputs = media_outputs
        self._workflow_debug = workflow_debug
        self._runtime_diagnostics = runtime_diagnostics

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
        workspace: DeepAgentsWorkspace | None = None,
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
                workspace=workspace,
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
        workflow_built: tuple[tuple[str, BuiltAgent], ...] = (),
        workflow_non_agent_filter: Callable[[OutputEvent], bool] | None = None,
        context: WorkflowRuntimeContext | None = None,
        run_config: dict[str, Any] | None = None,
        durability: str | None = None,
        debug_run: WorkflowDebugRun | None = None,
    ) -> AgentExecution:
        observers = []
        if event_observer is not None:
            observers.append(event_observer)
        workflow_agents = workflow_built or ((workflow_node_id, built),)
        if workflow_node_id:
            from agent_shell.workflow.events import WorkflowEventSourceV1

            workflow_sources = {
                node_id: WorkflowEventSourceV1(
                    source_type="agent",
                    workflow_node_id=node_id,
                    agent_profile_id=agent.agent_id,
                )
                for node_id, agent in workflow_agents
            }
            projector = WorkflowOutputProjector(
                {node_id: agent.output_config for node_id, agent in workflow_agents},
                non_agent_filter=workflow_non_agent_filter,
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
                main_agent_names=tuple(agent.agent_name for _, agent in workflow_agents),
                workflow_subagent_profile_ids={
                    node_id: agent.subagent_profile_ids
                    for node_id, agent in workflow_agents
                } if workflow_node_id else None,
                workflow_agent_names={
                    node_id: agent.agent_name
                    for node_id, agent in workflow_agents
                } if workflow_node_id else None,
            ),
            event_observers=tuple(observers),
            middleware_runtimes=tuple(
                agent.middleware_runtime
                for _, agent in workflow_agents[1:]
            ),
            context=context,
            run_config=run_config,
            durability=durability,
            debug_run=debug_run,
            runtime_diagnostics=self._runtime_diagnostics,
            request_id=request_id,
            public_model=public_model,
            agent_name=built.agent_name,
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
        context = WorkflowRuntimeContext.from_request(
            raw_messages,
            request_id=request_id,
            workflow={
                "filesystem_id": workflow_filesystem_id or "",
            },
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
        return self._execution(
            built,
            event_observer=event_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            public_model=public_model,
            context=context,
        )

    async def start_workflow(
        self,
        document: WorkflowGraphDocumentV1,
        raw_messages: object,
        *,
        workflow_filesystem_id: str,
        workflow_snapshot: Mapping[str, Any] | None = None,
        model_request_interceptor: Callable[[dict[str, Any]], Any] | None = None,
        model_request_observer: Callable[[dict[str, Any]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], None] | None = None,
        event_observer: Callable[[OutputEvent], None] | None = None,
        request_id: str = "",
        public_model: str = "",
        workflow_non_agent_filter: Callable[[OutputEvent], bool] | None = None,
    ) -> AgentExecution:
        from agent_shell.workflow.catalog import AgentNodeConfig
        from agent_shell.workflow.compiler import compile_workflow

        agent_nodes = [
            node for node in document.definition.nodes if node.type == "agent"
        ]
        context = WorkflowRuntimeContext.from_request(
            raw_messages,
            request_id=request_id,
            workflow={
                **dict(workflow_snapshot or {}),
                "filesystem_id": workflow_filesystem_id,
                "graph": document.model_dump(mode="json"),
            },
        )
        workflow_debug = getattr(self, "_workflow_debug", None)
        runtime_diagnostics = getattr(self, "_runtime_diagnostics", None)
        workflow_identity = dict(workflow_snapshot or {})
        debug_run = (
            workflow_debug.create_run(
                request_id=request_id,
                workflow_id=str(workflow_identity.get("id", "")),
                workflow_name=str(
                    workflow_identity.get("name", public_model or "workflow")
                ),
                messages_sha=context.messages_sha,
            )
            if workflow_debug is not None
            else None
        )
        if debug_run is not None:
            try:
                debug_run.begin()
            except Exception as exc:
                if runtime_diagnostics is not None:
                    runtime_diagnostics.observation_error(
                        exc,
                        request_id=request_id,
                        model=public_model,
                        agent_name="",
                        code="workflow_debug_record_failed",
                    )
        built_agents: list[tuple[str, BuiltAgent]] = []
        workspace = None
        try:
            for agent_node in agent_nodes:
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
                    workspace=workspace,
                )
                built_agents.append((agent_node.id, built))
                if workspace is None:
                    workspace = built.workspace
            if not built_agents:
                raise AgentRuntimeError(
                    "workflow.node_runtime_missing",
                    "The Workflow has no materialized runtime node.",
                    status_code=422,
                )
            graph = compile_workflow(
                document,
                node_graphs={node_id: agent.graph for node_id, agent in built_agents},
                checkpointer=(
                    workflow_debug.checkpointer
                    if workflow_debug is not None
                    else None
                ),
            )
        except asyncio.CancelledError:
            for _, agent in built_agents:
                await agent.middleware_runtime.close()
            if debug_run is not None:
                await debug_run.finish("cancelled", error_code="request_cancelled")
            raise
        except Exception as exc:
            for _, agent in built_agents:
                await agent.middleware_runtime.close()
            error_code = (
                exc.code
                if isinstance(exc, AgentRuntimeError)
                else "workflow_assembly_failed"
            )
            if runtime_diagnostics is not None:
                runtime_diagnostics.runtime_error(
                    exc,
                    request_id=request_id,
                    model=public_model,
                    agent_name="",
                    code=error_code,
                )
            if debug_run is not None:
                try:
                    await debug_run.finish(
                        "failed", error_code=error_code, error=exc
                    )
                except Exception as observation_error:
                    if runtime_diagnostics is not None:
                        runtime_diagnostics.observation_error(
                            observation_error,
                            request_id=request_id,
                            model=public_model,
                            agent_name="",
                            code="workflow_debug_record_failed",
                        )
            raise
        first_node_id, built = built_agents[0]
        return self._execution(
            built,
            graph=graph,
            workflow_node_id=first_node_id,
            workflow_built=tuple(built_agents),
            event_observer=event_observer,
            model_response_observer=model_response_observer,
            request_id=request_id,
            public_model=public_model,
            workflow_non_agent_filter=workflow_non_agent_filter,
            context=context,
            run_config=debug_run.config() if debug_run is not None else None,
            durability="sync" if debug_run is not None else None,
            debug_run=debug_run,
        )
