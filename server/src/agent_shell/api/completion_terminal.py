from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.session_recording import AgentRunCapture
from agent_shell.storage.agent_sessions import AgentRunStatus, AgentSessionStore
from agent_shell.storage.api_server import ApiServerStore, MessageHistoryStatus


class CompletionEventPublisher(Protocol):
    async def publish(self, event: dict[str, object]) -> None: ...

    def publish_nowait(self, event: dict[str, object]) -> None: ...


@dataclass(frozen=True, slots=True)
class CompletionTerminal:
    status: AgentRunStatus
    error_code: str | None
    response_text: str
    response_body: str
    response_content_type: str
    http_status: int
    finish_reason: str
    reasoning_tokens: int | None


@dataclass(frozen=True, slots=True)
class CompletionContext:
    request_id: str
    session_id: str
    model: str
    agent_name: str
    started_at: str
    request_body: str
    input_messages: object
    started_clock: float


class MessageHistoryRecorder:
    def __init__(
        self,
        store: ApiServerStore,
        events: CompletionEventPublisher,
        diagnostics: RuntimeDiagnostics,
    ) -> None:
        self._store = store
        self._events = events
        self._diagnostics = diagnostics

    async def record(
        self,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        started_at: str,
        status: MessageHistoryStatus,
        request_body: str,
        response_body: str | None,
        response_content_type: str | None,
        http_status: int | None,
        error_code: str | None,
    ) -> bool:
        try:
            self._store.add_message_history(
                request_id=request_id,
                model=model,
                agent_name=agent_name,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                status=status,
                request_body=request_body,
                response_body=response_body,
                response_content_type=response_content_type,
                http_status=http_status,
                error_code=error_code,
            )
            await self._events.publish({"type": "history_changed"})
        except Exception as exc:
            self._diagnostics.observation_error(
                exc,
                request_id=request_id,
                model=model,
                agent_name=agent_name,
                code="api_history_record_failed",
            )
            return False
        return True


class CompletionFinalizer:
    """Project one immutable completion terminal fact to all observers once."""

    def __init__(
        self,
        *,
        context: CompletionContext,
        capture: AgentRunCapture,
        diagnostics: RuntimeDiagnostics,
        agent_sessions: AgentSessionStore,
        events: CompletionEventPublisher,
        history: MessageHistoryRecorder,
    ) -> None:
        self._context = context
        self._capture = capture
        self._diagnostics = diagnostics
        self._agent_sessions = agent_sessions
        self._events = events
        self._history = history
        self._finalized = False

    def runtime_error(self, error: Exception, *, code: str) -> None:
        self._diagnostics.runtime_error(
            error,
            request_id=self._context.request_id,
            model=self._context.model,
            agent_name=self._context.agent_name,
            code=code,
        )

    async def finalize(self, terminal: CompletionTerminal) -> bool:
        if self._finalized:
            return False
        self._finalized = True

        if terminal.status in ("completed", "client_disconnected"):
            self._diagnostics.request_finished(
                request_id=self._context.request_id,
                model=self._context.model,
                agent_name=self._context.agent_name,
                status=terminal.status,
                duration_ms=int(
                    (time.monotonic() - self._context.started_clock) * 1000
                ),
                finish_reason=terminal.finish_reason,
                reasoning_tokens=terminal.reasoning_tokens,
            )

        self._record_agent_run(terminal)
        await self._history.record(
            request_id=self._context.request_id,
            model=self._context.model,
            agent_name=self._context.agent_name,
            started_at=self._context.started_at,
            status=terminal.status,
            request_body=self._context.request_body,
            response_body=terminal.response_body,
            response_content_type=terminal.response_content_type,
            http_status=terminal.http_status,
            error_code=terminal.error_code,
        )
        return True

    def _record_agent_run(self, terminal: CompletionTerminal) -> bool:
        try:
            self._agent_sessions.record_run(
                session_id=self._context.session_id,
                request_id=self._context.request_id,
                model=self._context.model,
                agent_name=self._context.agent_name,
                started_at=self._context.started_at,
                finished_at=datetime.now(timezone.utc).isoformat(
                    timespec="milliseconds"
                ),
                status=terminal.status,
                input_messages=self._context.input_messages,
                timeline=self._capture.snapshot(),
                response_text=terminal.response_text,
                error_code=terminal.error_code,
            )
            self._events.publish_nowait(
                {
                    "type": "agent_session_changed",
                    "session_id": self._context.session_id,
                }
            )
        except Exception as exc:
            self._diagnostics.observation_error(
                exc,
                request_id=self._context.request_id,
                model=self._context.model,
                agent_name=self._context.agent_name,
                code="agent_session_record_failed",
            )
            return False
        return True
