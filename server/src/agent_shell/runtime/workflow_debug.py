from __future__ import annotations

import threading
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_shell.redaction import redact_for_boundary
from agent_shell.runtime.limits import GRAPH_RECURSION_LIMIT
from agent_shell.storage.workflow_runs import WorkflowRunStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _label(value: object, *, limit: int = 240) -> str:
    safe = redact_for_boundary("request-trace", str(value or ""))
    text = safe if isinstance(safe, str) else "[UNAVAILABLE]"
    return text if len(text) <= limit else text[:limit]


def _run_name(serialized: object, kwargs: dict[str, Any]) -> str:
    explicit = kwargs.get("name")
    if explicit:
        return _label(explicit)
    if isinstance(serialized, dict):
        name = serialized.get("name")
        if name:
            return _label(name)
        identifier = serialized.get("id")
        if isinstance(identifier, (list, tuple)) and identifier:
            return _label(identifier[-1])
    return "unknown"


class WorkflowRunTreeCollector(BaseCallbackHandler):
    """Collect a bounded structural run tree without prompts or tool payloads."""

    def __init__(self, root_run_id: UUID, root_name: str) -> None:
        self._lock = threading.Lock()
        self._root_run_id = str(root_run_id)
        self._nodes: dict[str, dict[str, object]] = {
            str(root_run_id): {
                "run_id": str(root_run_id),
                "parent_run_id": None,
                "kind": "workflow",
                "name": _label(root_name),
                "status": "running",
                "started_at": _now(),
                "finished_at": None,
                "error_type": "",
                "tags": ["agent-shell", "workflow"],
                "metadata": {},
            }
        }

    @staticmethod
    def _metadata(value: dict[str, Any] | None) -> dict[str, str]:
        allowed = {
            "thread_id",
            "request_id",
            "workflow_id",
            "workflow_name",
            "messages_sha",
            "langgraph_node",
            "langgraph_step",
            "checkpoint_ns",
            "ls_provider",
            "ls_model_name",
        }
        return {
            str(key): _label(item)
            for key, item in (value or {}).items()
            if str(key) in allowed and item is not None
        }

    def _start(
        self,
        kind: str,
        serialized: object,
        *,
        run_id: UUID,
        parent_run_id: UUID | None,
        tags: list[str] | None,
        metadata: dict[str, Any] | None,
        kwargs: dict[str, Any],
    ) -> None:
        with self._lock:
            existing = self._nodes.get(str(run_id), {})
            is_root = str(run_id) == self._root_run_id
            self._nodes[str(run_id)] = {
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "kind": "workflow" if is_root else kind,
                "name": existing.get("name") if is_root else _run_name(serialized, kwargs),
                "status": "running",
                "started_at": existing.get("started_at") or _now(),
                "finished_at": None,
                "error_type": "",
                "tags": [_label(tag, limit=80) for tag in (tags or ())[:20]],
                "metadata": self._metadata(metadata),
            }

    def _finish(self, run_id: UUID, *, status: str, error: BaseException | None = None) -> None:
        with self._lock:
            node = self._nodes.setdefault(
                str(run_id),
                {
                    "run_id": str(run_id),
                    "parent_run_id": None,
                    "kind": "unknown",
                    "name": "unknown",
                    "started_at": _now(),
                    "tags": [],
                    "metadata": {},
                },
            )
            node["status"] = status
            node["finished_at"] = _now()
            node["error_type"] = type(error).__name__ if error is not None else ""

    def finish_root(self, root_run_id: UUID, *, status: str, error: BaseException | None) -> None:
        self._finish(root_run_id, status=status, error=error)

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return sorted(
                (dict(node) for node in self._nodes.values()),
                key=lambda item: (str(item.get("started_at", "")), str(item["run_id"])),
            )

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._start("chain", serialized, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, kwargs=kwargs)

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="completed")

    def on_chain_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="failed", error=error)

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._start("model", serialized, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, kwargs=kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._start("model", serialized, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, kwargs=kwargs)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, tags=None, **kwargs):
        self._finish(run_id, status="completed")

    def on_llm_error(self, error, *, run_id, parent_run_id=None, tags=None, **kwargs):
        self._finish(run_id, status="failed", error=error)

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, tags=None, metadata=None, inputs=None, **kwargs):
        self._start("tool", serialized, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, kwargs=kwargs)

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="completed")

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="failed", error=error)

    def on_retriever_start(self, serialized, query, *, run_id, parent_run_id=None, tags=None, metadata=None, **kwargs):
        self._start("retriever", serialized, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, kwargs=kwargs)

    def on_retriever_end(self, documents, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="completed")

    def on_retriever_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._finish(run_id, status="failed", error=error)


@dataclass(slots=True)
class WorkflowDebugRun:
    service: "WorkflowDebugService"
    thread_id: str
    run_id: UUID
    request_id: str
    workflow_id: str
    workflow_name: str
    messages_sha: str
    collector: WorkflowRunTreeCollector
    _started: bool = False
    _finished: bool = False

    def config(self) -> dict[str, object]:
        return {
            "recursion_limit": GRAPH_RECURSION_LIMIT,
            "configurable": {"thread_id": self.thread_id},
            "run_id": self.run_id,
            "run_name": f"workflow:{self.workflow_name}",
            "tags": ["agent-shell", "workflow"],
            "metadata": {
                "thread_id": self.thread_id,
                "request_id": self.request_id,
                "workflow_id": self.workflow_id,
                "workflow_name": self.workflow_name,
                "messages_sha": self.messages_sha,
            },
            "callbacks": [self.collector],
        }

    def begin(self) -> None:
        if self._started:
            return
        self._started = True
        self.service.store.begin(
            {
                "thread_id": self.thread_id,
                "run_id": str(self.run_id),
                "request_id": self.request_id,
                "workflow_id": self.workflow_id,
                "workflow_name": self.workflow_name,
                "messages_sha": self.messages_sha,
                "started_at": _now(),
                "langsmith_project": self.service.langsmith_project,
                "tracing_enabled": self.service.tracing_enabled,
                "run_tree": self.collector.snapshot(),
            }
        )

    async def finish(
        self,
        status: str,
        *,
        error_code: str = "",
        error: BaseException | None = None,
    ) -> None:
        if self._finished:
            return
        self._finished = True
        self.collector.finish_root(self.run_id, status=status, error=error)
        self.service.store.finish(
            thread_id=self.thread_id,
            status=status,
            finished_at=_now(),
            error_code=_label(error_code, limit=120),
            run_tree=self.collector.snapshot(),
        )


class WorkflowDebugService:
    def __init__(
        self,
        database_path: Path,
        store: WorkflowRunStore,
        *,
        tracing_enabled: bool,
        langsmith_project: str,
    ) -> None:
        self._database_path = database_path
        self.store = store
        self.tracing_enabled = tracing_enabled
        self.langsmith_project = langsmith_project
        self._context: AbstractAsyncContextManager[AsyncSqliteSaver] | None = None
        self._checkpointer: AsyncSqliteSaver | None = None

    @property
    def checkpointer(self) -> AsyncSqliteSaver:
        if self._checkpointer is None:
            raise RuntimeError("the Workflow checkpointer is not started")
        return self._checkpointer

    async def start(self) -> None:
        context = AsyncSqliteSaver.from_conn_string(str(self._database_path))
        checkpointer: AsyncSqliteSaver | None = None
        try:
            checkpointer = await context.__aenter__()
            await checkpointer.setup()
            self.store.cancel_running(finished_at=_now())
        except BaseException as exc:
            if checkpointer is not None:
                await context.__aexit__(type(exc), exc, exc.__traceback__)
            raise
        self._context = context
        self._checkpointer = checkpointer

    async def close(self) -> None:
        if self._context is not None:
            await self._context.__aexit__(None, None, None)
        self._context = None
        self._checkpointer = None

    def create_run(
        self,
        *,
        request_id: str,
        workflow_id: str,
        workflow_name: str,
        messages_sha: str,
        run_id: UUID | None = None,
        thread_id: str | None = None,
    ) -> WorkflowDebugRun:
        resolved_run_id = run_id or uuid4()
        return WorkflowDebugRun(
            service=self,
            thread_id=thread_id or str(uuid4()),
            run_id=resolved_run_id,
            request_id=request_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            messages_sha=messages_sha,
            collector=WorkflowRunTreeCollector(resolved_run_id, workflow_name),
        )

    async def checkpoint_history(
        self, thread_id: str, *, limit: int = 100
    ) -> list[dict[str, object]]:
        config = {"configurable": {"thread_id": thread_id}}
        result: list[dict[str, object]] = []
        async for item in self.checkpointer.alist(config, limit=limit):
            configurable = item.config.get("configurable", {})
            checkpoint = item.checkpoint
            metadata = item.metadata or {}
            channels = checkpoint.get("channel_values", {})
            result.append(
                {
                    "checkpoint_id": str(configurable.get("checkpoint_id", "")),
                    "checkpoint_ns": str(configurable.get("checkpoint_ns", "")),
                    "created_at": str(checkpoint.get("ts", "")),
                    "source": str(metadata.get("source", "")),
                    "step": metadata.get("step"),
                    "channel_names": sorted(str(key) for key in channels),
                    "pending_write_count": len(item.pending_writes or ()),
                }
            )
        return result

    async def detail(self, thread_id: str) -> dict[str, object] | None:
        run = self.store.get(thread_id)
        if run is None:
            return None
        return {**run, "checkpoints": await self.checkpoint_history(thread_id)}

    async def delete(self, thread_id: str) -> bool:
        return self.store.delete(thread_id)

    async def checkpoint_count(self, thread_id: str) -> int:
        config = {"configurable": {"thread_id": thread_id}}
        count = 0
        async for _ in self.checkpointer.alist(config):
            count += 1
        return count

    async def purge_thread(self, thread_id: str) -> bool:
        deleted = self.store.delete(thread_id)
        await self.checkpointer.adelete_thread(thread_id)
        return deleted


__all__ = [
    "WorkflowDebugRun",
    "WorkflowDebugService",
    "WorkflowRunTreeCollector",
]
