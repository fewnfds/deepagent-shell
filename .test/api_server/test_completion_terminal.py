from __future__ import annotations

import asyncio

from agent_shell.api.completion_terminal import (
    CompletionContext,
    CompletionFinalizer,
    CompletionTerminal,
)
from agent_shell.runtime.session_recording import AgentRunCapture


def test_completion_finalizer_projects_terminal_once() -> None:
    class Diagnostics:
        def __init__(self) -> None:
            self.finished: list[dict[str, object]] = []

        def request_finished(self, **fields: object) -> None:
            self.finished.append(fields)

        def observation_error(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("observation writes should succeed")

    class AgentSessions:
        def __init__(self) -> None:
            self.runs: list[dict[str, object]] = []

        def record_run(self, **fields: object) -> None:
            self.runs.append(fields)

    class Events:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []

        def publish_nowait(self, event: dict[str, object]) -> None:
            self.items.append(event)

    class History:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []

        async def record(self, **fields: object) -> bool:
            self.items.append(fields)
            return True

    diagnostics = Diagnostics()
    sessions = AgentSessions()
    events = Events()
    history = History()
    finalizer = CompletionFinalizer(
        context=CompletionContext(
            request_id="request-1",
            session_id="session-1",
            model="model-1",
            agent_name="Primary",
            started_at="2026-08-03T00:00:00.000Z",
            request_body='{"model":"model-1"}',
            input_messages=[],
            started_clock=0.0,
        ),
        capture=AgentRunCapture(),
        diagnostics=diagnostics,  # type: ignore[arg-type]
        agent_sessions=sessions,  # type: ignore[arg-type]
        events=events,  # type: ignore[arg-type]
        history=history,  # type: ignore[arg-type]
    )
    terminal = CompletionTerminal(
        status="completed",
        error_code=None,
        response_text="done",
        response_body='{"done":true}',
        response_content_type="application/json",
        http_status=200,
        finish_reason="stop",
        reasoning_tokens=3,
    )

    async def finalize_twice() -> tuple[bool, bool]:
        return await finalizer.finalize(terminal), await finalizer.finalize(terminal)

    first, second = asyncio.run(finalize_twice())

    assert first is True
    assert second is False
    assert len(diagnostics.finished) == 1
    assert len(sessions.runs) == 1
    assert len(history.items) == 1
    assert events.items == [
        {"type": "agent_session_changed", "session_id": "session-1"}
    ]
