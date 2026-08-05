from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from agent_shell.api.errors import management_error
from agent_shell.api.completion_terminal import (
    CompletionContext,
    CompletionFinalizer,
    CompletionTerminal,
    MessageHistoryRecorder,
)
from agent_shell.runtime.agent_runtime import AgentExecution
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.interception import InterceptionTestController
from agent_shell.runtime.input_messages import MAX_CHAT_COMPLETION_BODY_BYTES
from agent_shell.runtime.model_response import termination_block
from agent_shell.runtime.request_snapshot import RequestSnapshotRuntime
from agent_shell.runtime.session_recording import AgentRunCapture
from agent_shell.security import ApiKeyPolicyError, validate_api_key_policy
from agent_shell.settings import Settings, bearer_token_is_valid
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.agent_sessions import AgentRunStatus, AgentSessionStore
from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.validation.models import validation_failure_detail
from agent_shell.validation.service import ConfigurationValidationService

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class _ClientDisconnected(RuntimeError):
    pass


class _BodyTooLarge(RuntimeError):
    pass


async def _read_bounded_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError:
            pass
        else:
            if declared_length > limit:
                raise _BodyTooLarge

    body = bytearray()
    async for chunk in request.stream():
        if len(chunk) > limit - len(body):
            raise _BodyTooLarge
        body.extend(chunk)
    return bytes(body)


class ApiKeyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["keep", "replace", "clear"] = "keep"
    value: SecretStr | None = None

    @model_validator(mode="after")
    def validate_command(self) -> "ApiKeyCommand":
        if self.operation == "replace":
            if self.value is None:
                raise ValueError("replace requires an API Key")
            secret = self.value.get_secret_value()
            if not bearer_token_is_valid(secret):
                raise ValueError(
                    "API Key must be a non-empty printable ASCII value without spaces"
                )
        elif self.value is not None:
            raise ValueError("keep and clear do not accept an API Key value")
        return self


class ApiServerSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: ApiKeyCommand = Field(default_factory=ApiKeyCommand)
    max_initial_messages: int | None = Field(default=None, ge=1, le=10_000)


class ApiServerEventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, object]]] = set()

    async def publish(self, event: dict[str, object]) -> None:
        self.publish_nowait(event)

    def publish_nowait(self, event: dict[str, object]) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    async def stream(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield "data: " + json.dumps(
                    event, ensure_ascii=False, separators=(",", ":")
                ) + "\n\n"
        finally:
            self._subscribers.discard(queue)


def _openai_error(
    status_code: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_openai_error_payload(code, message, status_code=status_code, param=param),
    )


def _openai_error_payload(
    code: str,
    message: str,
    *,
    status_code: int,
    param: str | None = None,
) -> dict[str, object]:
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error" if status_code < 500 else "server_error",
            "param": param,
            "code": code,
        }
    }


def _internal_error_payload(request_id: str) -> dict[str, object]:
    payload = _openai_error_payload(
        "internal_error",
        "An internal operation failed.",
        status_code=500,
    )
    payload["request_id"] = request_id
    return payload


def _json_wire(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _model_object(model_id: str) -> dict[str, object]:
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "agent-shell",
    }


def _usage_payload(usage: dict[str, int]) -> dict[str, object]:
    payload: dict[str, object] = {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    reasoning_tokens = usage.get("reasoning_tokens")
    if reasoning_tokens is not None:
        payload["completion_tokens_details"] = {
            "reasoning_tokens": reasoning_tokens,
        }
    return payload


def _primary_completion_payload(
    model: str,
    content: str,
    usage: dict[str, int],
    finish_reason: str,
    finish_reason_source: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": f"chatcmpl_{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": _usage_payload(usage),
    }
    termination = termination_block(finish_reason, finish_reason_source)
    if termination is not None:
        payload["agent_shell"] = {"termination": termination}
    return payload


def build_api_server_router(
    store: ApiServerStore,
    agent_configs: AgentConfigStore,
    runtime: RequestSnapshotRuntime,
    settings: Settings,
    events: ApiServerEventHub,
    interception_tests: InterceptionTestController,
    diagnostics: RuntimeDiagnostics,
    agent_sessions: AgentSessionStore,
    validation: ConfigurationValidationService,
    media_outputs: MediaOutputStore,
) -> APIRouter:
    router = APIRouter()
    history = MessageHistoryRecorder(store, events, diagnostics)

    def public_settings(request: Request) -> dict[str, object]:
        current = store.settings()
        base = str(request.base_url).rstrip("/")
        return {
            "enabled": current["enabled"],
            "status": "running" if current["enabled"] else "stopped",
            "api_key": {"configured": bool(current["api_key_configured"])},
            "max_initial_messages": current["max_initial_messages"],
            "api_base_url": f"{base}/v1",
            "models_endpoint": f"{base}/v1/models",
            "chat_completions_endpoint": f"{base}/v1/chat/completions",
            "runtime": "model_streaming",
        }

    async def primary_completion_stream(
        *,
        execution: AgentExecution,
        model: str,
        finalizer: CompletionFinalizer,
    ) -> AsyncIterator[str]:
        completion_id = f"chatcmpl_{uuid4().hex}"
        created = int(time.time())
        wire: list[str] = []
        response_parts: list[str] = []
        terminal_status: AgentRunStatus = "client_disconnected"
        terminal_error_code: str | None = "client_disconnected"

        def encode(payload: dict[str, object]) -> str:
            item = "data: " + json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ) + "\n\n"
            wire.append(item)
            return item

        try:
            role = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None,
                    }
                ],
            }
            yield encode(role)
            try:
                async for text in execution.stream_text():
                    if not text:
                        continue
                    response_parts.append(text)
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": text},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield encode(chunk)
            except AgentRuntimeError as exc:
                terminal_status = "failed"
                terminal_error_code = exc.code
                finalizer.runtime_error(exc, code=exc.code)
                error_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "error"}
                    ],
                    "error": {
                        "message": exc.safe_message,
                        "type": "server_error",
                        "param": None,
                        "code": exc.code,
                    },
                }
                yield encode(error_chunk)
                wire.append("data: [DONE]\n\n")
                yield "data: [DONE]\n\n"
                return
            except Exception as exc:
                terminal_status = "failed"
                terminal_error_code = "internal_error"
                finalizer.runtime_error(exc, code="internal_error")
                error_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": "error"}
                    ],
                    "error": {
                        "message": "An internal operation failed.",
                        "type": "server_error",
                        "param": None,
                        "code": "internal_error",
                    },
                }
                yield encode(error_chunk)
                wire.append("data: [DONE]\n\n")
                yield "data: [DONE]\n\n"
                return

            finish = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": execution.finish_reason,
                    }
                ],
                "usage": _usage_payload(execution.usage),
            }
            termination = termination_block(
                execution.finish_reason,
                execution.finish_reason_source,
            )
            if termination is not None:
                finish["agent_shell"] = {"termination": termination}
            yield encode(finish)
            wire.append("data: [DONE]\n\n")
            yield "data: [DONE]\n\n"
            terminal_status = "completed"
            terminal_error_code = None
        finally:
            response_text = "".join(response_parts)
            await finalizer.finalize(
                CompletionTerminal(
                    status=terminal_status,
                    error_code=terminal_error_code,
                    response_text=response_text,
                    response_body="".join(wire),
                    response_content_type="text/event-stream",
                    http_status=200,
                    finish_reason=(
                        execution.finish_reason
                        if terminal_status == "completed"
                        else terminal_error_code or "unknown"
                    ),
                    reasoning_tokens=execution.usage.get("reasoning_tokens"),
                    response_blocks=execution.response_blocks,
                    media_assets=execution.media_assets,
                )
            )

    async def run_until_disconnect(
        execution: AgentExecution,
        request: Request,
    ) -> tuple[str, dict[str, int]]:
        async def wait_for_disconnect() -> None:
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    return

        execution_task = asyncio.create_task(execution.run())
        disconnect_task = asyncio.create_task(wait_for_disconnect())
        try:
            done, _ = await asyncio.wait(
                (execution_task, disconnect_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if execution_task in done:
                return execution_task.result()
            execution_task.cancel()
            with suppress(asyncio.CancelledError):
                await execution_task
            raise _ClientDisconnected
        finally:
            disconnect_task.cancel()
            with suppress(asyncio.CancelledError):
                await disconnect_task
            if not execution_task.done():
                execution_task.cancel()
                with suppress(asyncio.CancelledError):
                    await execution_task

    @router.get("/api/api-server")
    async def get_api_server_settings(request: Request) -> dict[str, object]:
        return public_settings(request)

    @router.put("/api/api-server", response_model=None)
    async def update_api_server_settings(
        payload: ApiServerSettingsUpdate, request: Request
    ) -> dict[str, object] | JSONResponse:
        secret = (
            payload.api_key.value.get_secret_value()
            if payload.api_key.value is not None
            else None
        )
        current_key = store.api_key()
        candidate_key = {
            "keep": current_key,
            "replace": secret,
            "clear": None,
        }[payload.api_key.operation]
        try:
            validate_api_key_policy(settings, candidate_key)
        except ApiKeyPolicyError as exc:
            raise management_error(
                422,
                code=exc.code,
                message_key=exc.message_key,
                message=exc.safe_message,
            )
        store.update_settings(
            api_key_operation=payload.api_key.operation,
            api_key=secret,
            max_initial_messages=payload.max_initial_messages,
        )
        await events.publish({"type": "settings_changed"})
        return public_settings(request)

    @router.post("/api/api-server/start")
    async def start_api_server(request: Request) -> dict[str, object]:
        store.set_enabled(False)
        report = validation.validate_api_start()
        if not report.valid:
            await events.publish({"type": "settings_changed"})
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(report),
            )
        store.set_enabled(True)
        await events.publish({"type": "settings_changed"})
        return public_settings(request)

    @router.post("/api/api-server/stop")
    async def stop_api_server(request: Request) -> dict[str, object]:
        store.set_enabled(False)
        await events.publish({"type": "settings_changed"})
        return public_settings(request)

    @router.get("/api/api-server/events")
    async def api_server_events() -> StreamingResponse:
        return StreamingResponse(
            events.stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/v1/models")
    async def models() -> JSONResponse:
        if not store.is_enabled():
            return _openai_error(503, "api_server_stopped", "The API server is stopped.")
        primary_models = [
            _model_object(item["name"])
            for item in agent_configs.list_items("primary_agents")
        ]
        return JSONResponse(content={"object": "list", "data": primary_models})

    @router.post("/v1/chat/completions", response_model=None)
    async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
        server_settings = store.settings()
        if not server_settings["enabled"]:
            return _openai_error(503, "api_server_stopped", "The API server is stopped.")
        try:
            body = await _read_bounded_body(request, MAX_CHAT_COMPLETION_BODY_BYTES)
        except _BodyTooLarge:
            return _openai_error(
                413,
                "input_body_too_large",
                f"The request body may not exceed {MAX_CHAT_COMPLETION_BODY_BYTES} bytes.",
            )
        try:
            raw_json = body.decode("utf-8")
            payload = json.loads(raw_json)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _openai_error(400, "invalid_json", "The request body must be valid UTF-8 JSON.")
        if not isinstance(payload, dict):
            return _openai_error(422, "invalid_request", "The request body must be a JSON object.")
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            return _openai_error(422, "model_required", "A model is required.", param="model")
        started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        try:
            request_snapshot = runtime.capture()
        except Exception as exc:
            diagnostics.runtime_error(
                exc,
                request_id=getattr(request.state, "request_id", ""),
                model=model,
                agent_name="",
                code="configuration_snapshot_failed",
            )
            error = _openai_error_payload(
                "configuration_snapshot_failed",
                "The current Agent configuration could not be captured.",
                status_code=500,
            )
            return JSONResponse(status_code=500, content=error)
        primary = request_snapshot.primary_by_name(model)
        if primary is None:
            return _openai_error(
                404,
                "model_not_found",
                "The requested model does not exist.",
                param="model",
            )
        agent_name = str(primary["name"])
        stream = payload.get("stream", False)
        if not isinstance(stream, bool):
            error = _openai_error_payload(
                "invalid_stream",
                "stream must be a boolean.",
                status_code=422,
                param="stream",
            )
            await history.record(
                request_id=getattr(request.state, "request_id", ""),
                model=model,
                agent_name=agent_name,
                started_at=started_at,
                status="failed",
                request_body=raw_json,
                response_body=_json_wire(error),
                response_content_type="application/json",
                http_status=422,
                error_code="invalid_stream",
            )
            return JSONResponse(status_code=422, content=error)
        input_messages = payload.get("messages")
        max_initial_messages = int(server_settings["max_initial_messages"])
        if isinstance(input_messages, list) and len(input_messages) > max_initial_messages:
            error = _openai_error_payload(
                "input_messages_too_many",
                f"messages cannot contain more than {max_initial_messages} items.",
                status_code=422,
                param="messages",
            )
            await history.record(
                request_id=getattr(request.state, "request_id", ""),
                model=model,
                agent_name=agent_name,
                started_at=started_at,
                status="failed",
                request_body=raw_json,
                response_body=_json_wire(error),
                response_content_type="application/json",
                http_status=422,
                error_code="input_messages_too_many",
            )
            return JSONResponse(status_code=422, content=error)
        if primary is not None:
            requested_session_id = request.headers.get("x-agent-session-id", "")
            if requested_session_id and not SESSION_ID_PATTERN.fullmatch(
                requested_session_id
            ):
                error = _openai_error_payload(
                    "invalid_agent_session_id",
                    "X-Agent-Session-ID must contain 1-120 letters, digits, dot, colon, underscore, or hyphen.",
                    status_code=422,
                    param=None,
                )
                await history.record(
                    request_id=getattr(request.state, "request_id", ""),
                    model=model,
                    agent_name=agent_name,
                    started_at=started_at,
                    status="failed",
                    request_body=raw_json,
                    response_body=_json_wire(error),
                    response_content_type="application/json",
                    http_status=422,
                    error_code="invalid_agent_session_id",
                )
                return JSONResponse(status_code=422, content=error)
            session_id = requested_session_id or f"session_{uuid4().hex}"
            session_headers = {"X-Agent-Session-ID": session_id}
            request_id = getattr(request.state, "request_id", "")
            request_started_clock = time.monotonic()
            capture = AgentRunCapture()
            finalizer = CompletionFinalizer(
                context=CompletionContext(
                    request_id=request_id,
                    session_id=session_id,
                    model=model,
                    agent_name=agent_name,
                    started_at=started_at,
                    request_body=raw_json,
                    input_messages=payload.get("messages"),
                    started_clock=request_started_clock,
                ),
                capture=capture,
                diagnostics=diagnostics,
                agent_sessions=agent_sessions,
                events=events,
                history=history,
                media_outputs=media_outputs,
            )

            diagnostics.request_started(
                request_id=request_id,
                model=model,
                agent_name=agent_name,
            )
            model_request_interceptor = None
            if interception_tests.is_enabled():
                def model_request_interceptor(
                    model_request: dict[str, object],
                ) -> None:
                    item = store.add_interception_record(
                        request_id=request_id,
                        model=model,
                        agent_name=agent_name,
                        request_raw_json=raw_json,
                        model_request_raw_json=json.dumps(
                            model_request,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    )
                    events.publish_nowait(
                        {"type": "interception_changed", "id": str(item["id"])}
                    )

            try:
                execution = await request_snapshot.start_agent(
                    str(primary["id"]),
                    payload.get("messages"),
                    model_request_interceptor=model_request_interceptor,
                    model_request_observer=capture.model_request,
                    agent_input_observer=capture.agent_input,
                    model_response_observer=capture.model_response,
                    event_observer=capture.output_event,
                    request_id=request_id,
                    public_model=model,
                )
            except AgentRuntimeError as exc:
                issue = (
                    exc.validation_report.issues[0]
                    if exc.validation_report is not None
                    and exc.validation_report.issues
                    else None
                )
                error_code = issue.code if issue is not None else exc.code
                error_message = issue.message if issue is not None else exc.safe_message
                finalizer.runtime_error(exc, code=error_code)
                error = _openai_error_payload(
                    error_code,
                    error_message,
                    status_code=exc.status_code,
                    param="model" if error_code.startswith("model_") else None,
                )
                await finalizer.finalize(
                    CompletionTerminal(
                        status="failed",
                        error_code=error_code,
                        response_text="",
                        response_body=_json_wire(error),
                        response_content_type="application/json",
                        http_status=exc.status_code,
                        finish_reason=error_code,
                        reasoning_tokens=None,
                    )
                )
                return JSONResponse(
                    status_code=exc.status_code, content=error, headers=session_headers
                )
            except Exception as exc:
                finalizer.runtime_error(exc, code="internal_error")
                error = _internal_error_payload(
                    getattr(request.state, "request_id", "")
                )
                await finalizer.finalize(
                    CompletionTerminal(
                        status="failed",
                        error_code="internal_error",
                        response_text="",
                        response_body=_json_wire(error),
                        response_content_type="application/json",
                        http_status=500,
                        finish_reason="internal_error",
                        reasoning_tokens=None,
                    )
                )
                return JSONResponse(
                    status_code=500, content=error, headers=session_headers
                )
            if stream:
                return StreamingResponse(
                    primary_completion_stream(
                        execution=execution,
                        model=model,
                        finalizer=finalizer,
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        **session_headers,
                    },
                )
            try:
                content, usage = await run_until_disconnect(execution, request)
            except _ClientDisconnected:
                await finalizer.finalize(
                    CompletionTerminal(
                        status="client_disconnected",
                        error_code="client_disconnected",
                        response_text="",
                        response_body="",
                        response_content_type="application/json",
                        http_status=499,
                        finish_reason="client_disconnected",
                        reasoning_tokens=execution.usage.get("reasoning_tokens"),
                        response_blocks=execution.response_blocks,
                        media_assets=execution.media_assets,
                    )
                )
                return Response(status_code=499, headers=session_headers)
            except AgentRuntimeError as exc:
                finalizer.runtime_error(exc, code=exc.code)
                error = _openai_error_payload(
                    exc.code,
                    exc.safe_message,
                    status_code=exc.status_code,
                )
                await finalizer.finalize(
                    CompletionTerminal(
                        status="failed",
                        error_code=exc.code,
                        response_text="",
                        response_body=_json_wire(error),
                        response_content_type="application/json",
                        http_status=exc.status_code,
                        finish_reason=exc.code,
                        reasoning_tokens=execution.usage.get("reasoning_tokens"),
                        response_blocks=execution.response_blocks,
                        media_assets=execution.media_assets,
                    )
                )
                return JSONResponse(
                    status_code=exc.status_code, content=error, headers=session_headers
                )
            except Exception as exc:
                finalizer.runtime_error(exc, code="internal_error")
                error = _internal_error_payload(
                    getattr(request.state, "request_id", "")
                )
                await finalizer.finalize(
                    CompletionTerminal(
                        status="failed",
                        error_code="internal_error",
                        response_text="",
                        response_body=_json_wire(error),
                        response_content_type="application/json",
                        http_status=500,
                        finish_reason="internal_error",
                        reasoning_tokens=execution.usage.get("reasoning_tokens"),
                        response_blocks=execution.response_blocks,
                        media_assets=execution.media_assets,
                    )
                )
                return JSONResponse(
                    status_code=500, content=error, headers=session_headers
                )
            response_payload = _primary_completion_payload(
                model,
                content,
                usage,
                execution.finish_reason,
                execution.finish_reason_source,
            )
            await finalizer.finalize(
                CompletionTerminal(
                    status="completed",
                    error_code=None,
                    response_text=content,
                    response_body=_json_wire(response_payload),
                    response_content_type="application/json",
                    http_status=200,
                    finish_reason=execution.finish_reason,
                    reasoning_tokens=usage.get("reasoning_tokens"),
                    response_blocks=execution.response_blocks,
                    media_assets=execution.media_assets,
                )
            )
            return JSONResponse(content=response_payload, headers=session_headers)

    return router
