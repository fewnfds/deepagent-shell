from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model
from langchain.tools import ToolRuntime

from agent_shell.runtime.prompt_preset import prepare_agent_input
from agent_shell.runtime.model_response import (
    ModelResponse,
    extract_provider_finish_reason,
)


_worker_tool_call_id: ContextVar[str] = ContextVar(
    "context_worker_tool_call_id", default=""
)


@dataclass(frozen=True, slots=True)
class ContextWorkerSpec:
    name: str
    graph: Any
    preset: dict[str, Any]
    include_client_messages: bool
    initial_files: dict[str, Any]


def worker_args_model(
    worker_names: tuple[str, ...],
    *,
    worker_description: str,
    task_description: str,
) -> type[BaseModel]:
    worker_type = Literal.__getitem__(worker_names)
    return create_model(
        "RunContextWorkerArguments",
        __config__=ConfigDict(arbitrary_types_allowed=True),
        worker=(worker_type, Field(description=worker_description)),
        task=(
            str,
            Field(min_length=1, max_length=100_000, description=task_description),
        ),
        runtime=(ToolRuntime, ...),
    )


def make_guarded_worker_tool(
    *,
    args_schema: type[BaseModel],
    description: str,
) -> Any:
    from langchain_core.tools import StructuredTool

    async def reject_nested_worker(
        worker: str, task: str, runtime: ToolRuntime
    ) -> str:
        del worker, task, runtime
        return json.dumps(
            {
                "status": "error",
                "error_code": "context_worker_recursion_rejected",
            },
            separators=(",", ":"),
        )

    return StructuredTool.from_function(
        coroutine=reject_nested_worker,
        name="run_worker",
        description=description,
        args_schema=args_schema,
    )


class ContextWorkerRuntime:
    def __init__(
        self,
        specs: tuple[ContextWorkerSpec, ...],
        client_messages: list[dict[str, str]],
        *,
        args_schema: type[BaseModel],
        description: str,
        max_calls: int,
        max_parallel: int,
        agent_input_observer: Callable[[dict[str, object]], Any] | None = None,
        model_response_observer: Callable[[ModelResponse], Any] | None = None,
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        self._client_messages = [dict(message) for message in client_messages]
        self._args_schema = args_schema
        self._description = description
        self._max_calls = max_calls
        self._calls = 0
        self._call_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._agent_input_observer = agent_input_observer
        self._model_response_observer = model_response_observer

    def tool(self) -> Any:
        from langchain_core.tools import StructuredTool

        return StructuredTool.from_function(
            coroutine=self._run,
            name="run_worker",
            description=self._description,
            args_schema=self._args_schema,
        )

    async def _run(self, worker: str, task: str, runtime: ToolRuntime) -> str:
        spec = self._specs.get(worker)
        if spec is None:
            self._emit(runtime, worker, "error", "context_worker_not_allowed")
            return self._error("context_worker_not_allowed", worker)
        async with self._call_lock:
            if self._calls >= self._max_calls:
                self._emit(
                    runtime, worker, "error", "context_worker_call_limit_reached"
                )
                return self._error("context_worker_call_limit_reached", worker)
            self._calls += 1

        self._emit(runtime, worker, "start", "")
        try:
            async with self._semaphore:
                source_messages = self._client_messages if spec.include_client_messages else []
                prepared = prepare_agent_input(
                    source_messages,
                    spec.preset,
                    variables={
                        "agent_name": spec.name,
                        "worker_name": spec.name,
                        "task": task,
                        "workspace": "/",
                    },
                )
                if self._agent_input_observer is not None:
                    self._agent_input_observer(
                        {
                            "agent_type": "context_worker",
                            "agent_name": worker,
                            "tool_call_id": runtime.tool_call_id or "",
                            "message_count": len(prepared.messages),
                            "matched_tag_count": prepared.matched_tag_count,
                            "startup_message_count": prepared.startup_message_count,
                        }
                    )
                state: dict[str, Any] = {"messages": prepared.messages}
                if spec.initial_files:
                    state["files"] = dict(spec.initial_files)
                token = _worker_tool_call_id.set(runtime.tool_call_id or "")
                try:
                    result = await spec.graph.ainvoke(state)
                finally:
                    _worker_tool_call_id.reset(token)
                self._observe_model_responses(
                    result,
                    initial_message_count=len(prepared.messages),
                    worker=worker,
                    tool_call_id=runtime.tool_call_id or "",
                )
                text = self._result_text(result)
                self._emit(runtime, worker, "end", "")
                return text
        except Exception:
            self._emit(runtime, worker, "error", "context_worker_execution_failed")
            return self._error("context_worker_execution_failed", worker)

    @staticmethod
    def _emit(
        runtime: ToolRuntime,
        worker: str,
        phase: str,
        error_code: str,
    ) -> None:
        runtime.stream_writer(
            {
                "event_type": "context_worker",
                "phase": phase,
                "worker_name": worker,
                "tool_call_id": runtime.tool_call_id or "",
                "status": "failed" if phase == "error" else "running" if phase == "start" else "completed",
                "error_code": error_code,
            }
        )

    @staticmethod
    def _result_text(result: Any) -> str:
        if isinstance(result, dict):
            structured = result.get("structured_response")
            if structured is not None:
                if hasattr(structured, "model_dump"):
                    structured = structured.model_dump(mode="json")
                return json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
            messages = result.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    if getattr(message, "type", "") == "ai":
                        text = getattr(message, "text", "")
                        if isinstance(text, str):
                            return text
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        content = message.get("content")
                        if isinstance(content, str):
                            return content
        return json.dumps(
            {"status": "error", "error_code": "context_worker_result_missing"},
            separators=(",", ":"),
        )

    def _observe_model_responses(
        self,
        result: Any,
        *,
        initial_message_count: int,
        worker: str,
        tool_call_id: str,
    ) -> None:
        if self._model_response_observer is None or not isinstance(result, dict):
            return
        messages = result.get("messages")
        if not isinstance(messages, list):
            return
        for message in messages[initial_message_count:]:
            if getattr(message, "type", "") != "ai":
                continue
            usage = getattr(message, "usage_metadata", None)
            response_metadata = getattr(message, "response_metadata", None)
            additional_kwargs = getattr(message, "additional_kwargs", None)
            metadata = response_metadata if isinstance(response_metadata, dict) else {}
            reason, source = extract_provider_finish_reason(metadata)
            content_blocks = getattr(message, "content_blocks", None)
            self._model_response_observer(
                ModelResponse(
                    timestamp=datetime.now(timezone.utc).isoformat(
                        timespec="milliseconds"
                    ),
                    namespace=f"context_worker/{tool_call_id}",
                    agent_name=worker,
                    node="model",
                    run_id="",
                    message_id=str(getattr(message, "id", "") or ""),
                    is_primary=False,
                    usage=dict(usage) if isinstance(usage, dict) else {},
                    response_metadata=dict(metadata),
                    additional_kwargs=(
                        dict(additional_kwargs)
                        if isinstance(additional_kwargs, dict)
                        else {}
                    ),
                    content_blocks=(
                        [dict(block) for block in content_blocks if isinstance(block, dict)]
                        if isinstance(content_blocks, list)
                        else []
                    ),
                    provider_finish_reason=reason,
                    finish_reason_source=source,
                )
            )

    @staticmethod
    def _error(code: str, worker: str) -> str:
        return json.dumps(
            {"status": "error", "error_code": code, "worker": worker},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def build_context_worker_tool(
    resolved_workers: tuple[Any, ...],
    client_messages: list[dict[str, str]],
    delegation: dict[str, Any],
    *,
    primary_id: str,
    materialize_profile: Callable[..., dict[str, Any]],
    validate_middleware_names: Callable[..., None],
    validate_tool_names: Callable[..., None],
    agent_input_observer: Callable[[dict[str, object]], Any] | None,
    model_request_observer: Callable[[dict[str, Any]], Any] | None,
    model_response_observer: Callable[[ModelResponse], Any] | None,
) -> Any:
    from langchain.agents import create_agent

    from agent_shell.runtime.limits import (
        ProviderErrorBoundaryMiddleware,
        ToolErrorBoundaryMiddleware,
    )
    from agent_shell.runtime.model_request_settings import (
        make_model_request_settings_middleware,
    )
    from agent_shell.runtime.interception import (
        make_model_request_observer_middleware,
    )

    worker_names = tuple(str(item.binding["name"]) for item in resolved_workers)
    args_schema = worker_args_model(
        worker_names,
        worker_description=str(delegation["worker_parameter_description"]),
        task_description=str(delegation["task_parameter_description"]),
    )
    guarded_tool = make_guarded_worker_tool(
        args_schema=args_schema,
        description=str(delegation["tool_description"]),
    )
    specs: list[ContextWorkerSpec] = []
    for resolved in resolved_workers:
        worker_name = str(resolved.binding["name"])
        materialized = materialize_profile(
            resolved.references,
            resolved.blocks,
            filesystem_mode=resolved.filesystem_mode,
            scope="context_worker",
            owner_id=primary_id,
            owner_name=worker_name,
        )
        tools = [*materialized["tools"], guarded_tool]
        middleware = [ToolErrorBoundaryMiddleware(), *materialized["middleware"]]
        if materialized["tool_choice"] is not None or materialized["model_settings"]:
            middleware.append(
                make_model_request_settings_middleware(
                    tool_choice=materialized["tool_choice"],
                    model_settings=materialized["model_settings"],
                )
            )
        middleware.extend(materialized["custom_middleware"])
        if model_request_observer is not None:
            middleware.append(
                make_model_request_observer_middleware(
                    model_request_observer,
                    context=lambda worker_name=worker_name: {
                        "agent_type": "context_worker",
                        "agent_name": worker_name,
                        "tool_call_id": _worker_tool_call_id.get(),
                    },
                )
            )
        middleware.append(ProviderErrorBoundaryMiddleware())
        retry = materialized["exception_retry"]
        if retry is not None:
            middleware.extend(retry.after_provider_boundary)
        validate_middleware_names(
            middleware,
            owner=f"Context Worker {worker_name}",
        )
        validate_tool_names(
            tools=tools,
            middleware=middleware,
            owner=f"Context Worker {worker_name}",
        )
        constructor: dict[str, Any] = {
            "model": materialized["model"],
            "name": worker_name,
            "tools": tools,
            "middleware": middleware,
        }
        if materialized["system_prompt"] is not None:
            constructor["system_prompt"] = materialized["system_prompt"]
        if materialized["response_format"] is not None:
            constructor["response_format"] = materialized["response_format"]
        specs.append(
            ContextWorkerSpec(
                name=worker_name,
                graph=create_agent(**constructor),
                preset=resolved.blocks["prompt-preset"],
                include_client_messages=bool(
                    resolved.profile["include_client_messages"]
                ),
                initial_files=dict(materialized["initial_files"]),
            )
        )

    return ContextWorkerRuntime(
        tuple(specs),
        client_messages,
        args_schema=args_schema,
        description=str(delegation["tool_description"]),
        max_calls=int(delegation["max_worker_calls_per_request"]),
        max_parallel=int(delegation["max_parallel_workers"]),
        agent_input_observer=agent_input_observer,
        model_response_observer=model_response_observer,
    ).tool()
