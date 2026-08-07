from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.storage.graph_runs import GraphRunStore
from agent_shell.workflow.artifacts import ArtifactCommitter
from agent_shell.workflow.compiler import CompiledWorkflow
from agent_shell.workflow.context import GraphRunControl, WorkflowContext


GraphFactory = Callable[
    [str, Callable[[dict[str, Any]], None], list[dict[str, Any]], str, ArtifactCommitter | None],
    Awaitable[CompiledWorkflow],
]
ArtifactCommitterFactory = Callable[[str, Callable[[dict[str, Any]], None]], ArtifactCommitter | None]
GraphRunErrorReporter = Callable[[BaseException, str], None]


@dataclass(slots=True)
class _ActiveRun:
    run_id: str
    thread_id: str
    control: GraphRunControl
    task: asyncio.Task[None] | None = None
    queues: list[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=list)


class GraphRunService:
    """Management-facing lifecycle around a compiled LangGraph.

    LangGraph owns scheduling, retry and checkpoints.  This service owns only
    run identity, control intent, event projection and the UI's subscription.
    """

    def __init__(self, store: GraphRunStore, graph_factory: GraphFactory, checkpointer: Any = None, entry_script_lookup: Callable[[str], dict[str, Any] | None] | None = None, artifact_committer_factory: ArtifactCommitterFactory | None = None, error_reporter: GraphRunErrorReporter | None = None) -> None:
        self._store = store
        self._factory = graph_factory
        self._checkpointer = checkpointer
        self._entry_script_lookup = entry_script_lookup
        self._artifact_committer_factory = artifact_committer_factory
        self._error_reporter = error_reporter
        self._active: dict[str, _ActiveRun] = {}
        self._lock = asyncio.Lock()

    def list_runs(self, graph_id: str | None = None) -> list[dict[str, Any]]:
        return self._store.list(graph_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._store.get(run_id)

    async def start(self, graph_id: str, *, messages: list[dict[str, Any]], entry_script_id: str | None = None, run_id: str | None = None, resume: bool = False) -> dict[str, Any]:
        async with self._lock:
            if resume:
                if not run_id:
                    raise AgentRuntimeError("graph_run_id_required", "A run id is required to resume a run.", status_code=422)
                item = self._store.get(run_id)
                if item is None:
                    raise AgentRuntimeError("graph_run_not_found", "The graph run does not exist.", status_code=404)
                if item["status"] not in {"cancelled", "paused", "failed"}:
                    raise AgentRuntimeError("graph_run_not_resumable", "The graph run is not resumable in its current state.", status_code=409)
                graph_id = str(item["graph_id"])
                thread_id = str(item["thread_id"])
                entry_script_id = item.get("entry_script_id")
                saved_input = item.get("input")
                if isinstance(saved_input, dict) and isinstance(saved_input.get("messages"), list):
                    messages = list(saved_input["messages"])
            else:
                run_id = run_id or str(uuid4())
                thread_id = run_id
                self._store.create(run_id=run_id, graph_id=graph_id, thread_id=thread_id, entry_script_id=entry_script_id, input_value={"messages": messages})
            if run_id in self._active and not self._active[run_id].task.done():
                raise AgentRuntimeError("graph_run_already_active", "The graph run is already active.", status_code=409)
            active = _ActiveRun(run_id=run_id, thread_id=thread_id, control=GraphRunControl())
            self._active[run_id] = active
            active.task = asyncio.create_task(self._execute(active, graph_id, messages, resume, entry_script_id), name=f"graph-run:{run_id}")
            return self._store.update(run_id, status="running") or {}

    async def _execute(self, active: _ActiveRun, graph_id: str, messages: list[dict[str, Any]], resume: bool, entry_script_id: str | None) -> None:
        def emit(event: dict[str, Any]) -> None:
            payload = {"type": "graph_run", "run_id": active.run_id, **event}
            self._store.update(active.run_id, state=payload.get("state") if isinstance(payload.get("state"), dict) else None)
            for queue in tuple(active.queues):
                queue.put_nowait(payload)

        compiled: CompiledWorkflow | None = None
        terminal: dict[str, Any] = {"status": "failed", "error_code": "graph_run_failed"}
        agents_started = False
        prepared_state: dict[str, Any] = {}
        try:
            shared: dict[str, Any] = {}
            if not resume and entry_script_id and self._entry_script_lookup is not None:
                entry = self._entry_script_lookup(entry_script_id)
                if entry is None:
                    raise AgentRuntimeError("entry_script_not_found", "The Entry Script does not exist.", status_code=404)
                if str(entry.get("graph_id") or "") != graph_id:
                    raise AgentRuntimeError("entry_script_graph_mismatch", "The Entry Script targets a different Graph.", status_code=409)
                if not entry.get("enabled", True):
                    raise AgentRuntimeError("entry_script_disabled", "The Entry Script is disabled.", status_code=409)
                source = str(entry.get("source") or "")
                if source:
                    namespace: dict[str, Any] = {"__builtins__": __builtins__}
                    try:
                        exec(compile(source, "<entry-script>", "exec"), namespace, namespace)
                        prepare = namespace.get("prepare")
                        if not callable(prepare):
                            raise ValueError("prepare is required")
                        result = prepare(messages)
                        if not isinstance(result, dict):
                            raise ValueError("prepare must return an object")
                        if isinstance(result.get("messages"), list):
                            messages = result["messages"]
                        for key in ("inputs", "shared", "control", "artifacts", "ports", "output"):
                            value = result.get(key)
                            if isinstance(value, dict):
                                prepared_state[key] = dict(value)
                        shared = dict(prepared_state.get("shared") or {})
                    except Exception as exc:
                        raise AgentRuntimeError("entry_script_failed", "The Entry Script failed during preparation.", status_code=422) from exc
            committer = self._artifact_committer_factory(active.run_id, emit) if self._artifact_committer_factory is not None else None
            compiled = await self._factory(graph_id, emit, messages, active.run_id, committer)
            agents_started = compiled.start is not None
            if resume and getattr(compiled.graph, "checkpointer", None) is None:
                raise AgentRuntimeError("graph_checkpoint_unavailable", "The Graph cannot resume because no checkpoint backend is configured.", status_code=409)
            context = WorkflowContext(
                request_id=active.run_id,
                workflow_id=graph_id,
                invocation_id=active.run_id,
                control=active.control,
                emit=emit,
                agent_contexts=compiled.agent_contexts,
            )
            if compiled.start is not None:
                await compiled.start()
            input_value: dict[str, Any] | None = None if resume else {
                "messages": messages,
                "inputs": {"messages": messages, **dict(prepared_state.get("inputs") or {})},
                "shared": shared,
                "control": dict(prepared_state.get("control") or {}),
                **{key: value for key, value in prepared_state.items() if key not in {"inputs", "shared", "control"}},
            }
            config = {
                "configurable": {"thread_id": active.thread_id},
                "recursion_limit": compiled.definition.recursion_limit,
            }
            kwargs: dict[str, Any] = {"context": context, "config": config, "stream_mode": ["updates", "values"], "version": "v2", "subgraphs": True}
            if getattr(compiled.graph, "checkpointer", None) is not None:
                kwargs["durability"] = "sync"
            async for event in compiled.graph.astream(input_value, **kwargs):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "values":
                    state = event.get("data")
                    if isinstance(state, dict):
                        self._store.update(active.run_id, state=state)
                        emit({"event": "state", "state": state})
                elif event.get("type") == "updates":
                    data = event.get("data")
                    if isinstance(data, dict):
                        for node_id, update in data.items():
                            emit({"event": "node_update", "node_id": node_id, "update": update, "namespace": event.get("ns", ())})
            self._store.update(active.run_id, status="completed")
            emit({"event": "completed"})
            terminal = {"status": "completed"}
        except asyncio.CancelledError:
            self._store.update(active.run_id, status="cancelled")
            emit({"event": "cancelled"})
            terminal = {"status": "cancelled", "error_code": "request_cancelled"}
        except AgentRuntimeError as exc:
            self._store.update(active.run_id, status="failed", error_code=exc.code)
            emit({"event": "failed", "error_code": exc.code, "message": exc.safe_message})
            terminal = {"status": "failed", "error_code": exc.code}
        except Exception as exc:
            if self._error_reporter is not None:
                self._error_reporter(exc, active.run_id)
            self._store.update(active.run_id, status="failed", error_code="graph_run_failed")
            emit({"event": "failed", "error_code": "graph_run_failed"})
        finally:
            try:
                if compiled is not None and compiled.finish is not None and agents_started:
                    await compiled.finish(terminal)
            except Exception:
                self._store.update(active.run_id, status="failed", error_code="graph_run_cleanup_failed")
                emit({"event": "failed", "error_code": "graph_run_cleanup_failed"})
            finally:
                try:
                    if compiled is not None and compiled.cleanup is not None:
                        compiled.cleanup()
                finally:
                    for queue in tuple(active.queues):
                        queue.put_nowait(None)
                    self._active.pop(active.run_id, None)

    async def pause(self, run_id: str) -> dict[str, Any]:
        active = self._require_active(run_id)
        active.control.pause()
        return self._store.update(run_id, status="paused") or {}

    async def resume(self, run_id: str) -> dict[str, Any]:
        active = self._active.get(run_id)
        if active is not None:
            active.control.resume()
            return self._store.update(run_id, status="running") or {}
        return await self.start("", messages=[], run_id=run_id, resume=True)

    async def cancel(self, run_id: str) -> dict[str, Any]:
        active = self._require_active(run_id)
        active.control.cancel()
        if active.task is not None:
            active.task.cancel()
        return self._store.update(run_id, status="cancelled") or {}

    def _require_active(self, run_id: str) -> _ActiveRun:
        active = self._active.get(run_id)
        if active is None or active.task is None or active.task.done():
            raise AgentRuntimeError("graph_run_not_active", "The graph run is not active.", status_code=409)
        return active

    async def stream(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        item = self._store.get(run_id)
        if item is None:
            raise AgentRuntimeError("graph_run_not_found", "The graph run does not exist.", status_code=404)
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        active = self._active.get(run_id)
        if active is not None:
            active.queues.append(queue)
        else:
            yield {"type": "graph_run", "run_id": run_id, "event": "snapshot", "run": item}
            return
        try:
            yield {"type": "graph_run", "run_id": run_id, "event": "snapshot", "run": item}
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            if active is not None and queue in active.queues:
                active.queues.remove(queue)
