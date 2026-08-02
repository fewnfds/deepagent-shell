from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from agent_shell.runtime.output_projection import OutputProjector, StreamProjection
from agent_shell.runtime.output_stream import OutputEvent

TOOL_OUTCOME_TYPES = {"tool_result", "tool_error"}


@dataclass(slots=True)
class _PendingEvent:
    event: OutputEvent
    projection: StreamProjection | None = None
    text: str = ""
    sent_length: int = 0
    last_activity: float = 0.0
    ready: bool = False

    @property
    def streamable(self) -> bool:
        return self.projection is not None


@dataclass(slots=True)
class _SourceState:
    event: OutputEvent
    text: str = ""
    pending: _PendingEvent | None = None
    closed: bool = False


class OutputEventRectifier:
    """Serialize public output events without trusting delayed block finishes."""

    def __init__(
        self,
        projector: OutputProjector,
        *,
        quiet_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._projector = projector
        self._quiet_seconds = quiet_seconds
        self._clock = clock
        self._queue: deque[_PendingEvent] = deque()
        self._sources: dict[str, _SourceState] = {}
        self._current: _PendingEvent | None = None

    @property
    def next_deadline(self) -> float | None:
        if self._current is None or not self._queue:
            return None
        return self._current.last_activity + self._quiet_seconds

    def deadline_delay(self) -> float | None:
        deadline = self.next_deadline
        return None if deadline is None else max(0.0, deadline - self._clock())

    def feed(self, event: OutputEvent, *, now: float | None = None) -> list[str]:
        observed_at = self._clock() if now is None else now
        if event.stream_id:
            parts = self._feed_source_event(event, observed_at)
        else:
            parts = self._feed_atomic_event(event, observed_at)
        parts.extend(self._drain(observed_at))
        return parts

    def expire(self, *, now: float | None = None) -> list[str]:
        observed_at = self._clock() if now is None else now
        deadline = self.next_deadline
        if deadline is None or observed_at < deadline:
            return []
        parts = self._close_current()
        parts.extend(self._drain(observed_at))
        return parts

    def flush(self) -> list[str]:
        parts: list[str] = []
        if self._current is not None:
            parts.extend(self._close_current())
        while self._queue:
            item = self._queue.popleft()
            if item.streamable:
                parts.extend(self._activate(item))
                parts.extend(self._close_current())
            elif item.ready:
                parts.extend(self._render_atomic_with_pair(item))
        self._sources.clear()
        return parts

    def abort(self) -> list[str]:
        parts = self._close_current() if self._current is not None else []
        self.discard()
        return parts

    def discard(self) -> None:
        self._queue.clear()
        self._sources.clear()
        self._current = None

    def _feed_source_event(self, event: OutputEvent, now: float) -> list[str]:
        source = self._sources.get(event.stream_id)
        if event.phase == "start":
            if not self._projector.enabled(event) or source is not None:
                return []
            source = _SourceState(event=event)
            self._sources[event.stream_id] = source
            projection = self._projector.stream_projection(event)
            pending = _PendingEvent(
                event=event,
                projection=projection,
                last_activity=now,
                ready=projection is not None,
            )
            source.pending = pending
            self._queue.append(pending)
            return []
        if source is None:
            if event.phase == "end" and self._projector.enabled(event):
                return self._feed_atomic_event(event, now)
            return []
        if event.phase == "delta":
            return self._append_source_text(source, event.message, now)
        if event.phase == "end":
            return self._finish_source(source, event, now)
        return []

    def _append_source_text(
        self, source: _SourceState, fragment: str, now: float
    ) -> list[str]:
        if not fragment:
            return []
        source.text += fragment
        pending = source.pending
        if pending is None or source.closed:
            projection = self._projector.stream_projection(source.event)
            if projection is None:
                return []
            pending = _PendingEvent(
                event=source.event,
                projection=projection,
                last_activity=now,
                ready=True,
            )
            source.pending = pending
            source.closed = False
            self._queue.append(pending)
        pending.text += fragment
        pending.last_activity = now
        if pending is self._current:
            pending.sent_length = len(pending.text)
            return [self._projector.encode_message(fragment)]
        return []

    def _finish_source(
        self, source: _SourceState, event: OutputEvent, now: float
    ) -> list[str]:
        if event.message.startswith(source.text):
            tail = event.message[len(source.text) :]
            parts = self._append_source_text(source, tail, now)
        else:
            parts = []
        pending = source.pending
        if pending is not None and not pending.streamable:
            pending.event = event
            pending.ready = True
        return parts

    def _feed_atomic_event(self, event: OutputEvent, now: float) -> list[str]:
        if not self._projector.enabled(event):
            return []
        self._queue.append(
            _PendingEvent(
                event=event,
                text=event.message,
                last_activity=now,
                ready=True,
            )
        )
        return []

    def _drain(self, now: float) -> list[str]:
        parts: list[str] = []
        while self._current is None and self._queue:
            item = self._next_ready_item()
            if item is None:
                break
            self._queue.remove(item)
            if item.streamable:
                parts.extend(self._activate(item))
                if self._queue and now >= item.last_activity + self._quiet_seconds:
                    parts.extend(self._close_current())
                    continue
                break
            parts.extend(self._render_atomic_with_pair(item))
        return parts

    def _next_ready_item(self) -> _PendingEvent | None:
        """Keep tool calls pool-local until their outcome or a cycle flush."""

        unmatched_tool_call_seen = False
        for candidate in self._queue:
            if not candidate.ready:
                continue
            event_type = candidate.event.event_type
            if event_type == "tool_call":
                call_id = candidate.event.values.get("tool_call_id", "")
                if not call_id:
                    return candidate
                if self._find_tool_partner(candidate) is None:
                    unmatched_tool_call_seen = True
                    continue
                if not unmatched_tool_call_seen:
                    return candidate
                continue
            if event_type in TOOL_OUTCOME_TYPES:
                if self._find_tool_partner(candidate) is None:
                    return candidate
                # A queued call owns the pair's position and output order.
                continue
            return candidate
        return None

    def _activate(self, item: _PendingEvent) -> list[str]:
        self._current = item
        parts = (
            [item.projection.prefix]
            if item.projection and item.projection.prefix
            else []
        )
        if item.sent_length < len(item.text):
            unsent = item.text[item.sent_length :]
            item.sent_length = len(item.text)
            encoded = self._projector.encode_message(unsent)
            if encoded:
                parts.append(encoded)
        return parts

    def _close_current(self) -> list[str]:
        item = self._current
        if item is None:
            return []
        parts: list[str] = []
        if item.sent_length < len(item.text):
            unsent = item.text[item.sent_length :]
            item.sent_length = len(item.text)
            encoded = self._projector.encode_message(unsent)
            if encoded:
                parts.append(encoded)
        if item.projection and item.projection.suffix:
            parts.append(item.projection.suffix)
        self._current = None
        source_id = item.event.stream_id
        source = self._sources.get(source_id)
        if source is not None and source.pending is item:
            source.closed = True
        return parts

    def _render_atomic_with_pair(self, item: _PendingEvent) -> list[str]:
        partner = self._take_tool_partner(item)
        ordered = [item]
        if partner is not None:
            if item.event.event_type in TOOL_OUTCOME_TYPES:
                ordered = [partner, item]
            else:
                ordered.append(partner)
        return [
            rendered
            for candidate in ordered
            if (rendered := self._projector.render(candidate.event))
        ]

    def _take_tool_partner(self, item: _PendingEvent) -> _PendingEvent | None:
        partner = self._find_tool_partner(item)
        if partner is not None:
            self._queue.remove(partner)
        return partner

    def _find_tool_partner(self, item: _PendingEvent) -> _PendingEvent | None:
        event_type = item.event.event_type
        if event_type != "tool_call" and event_type not in TOOL_OUTCOME_TYPES:
            return None
        call_id = item.event.values.get("tool_call_id", "")
        if not call_id:
            return None
        for candidate in self._queue:
            candidate_type = candidate.event.event_type
            complementary = (
                event_type == "tool_call" and candidate_type in TOOL_OUTCOME_TYPES
            ) or (
                event_type in TOOL_OUTCOME_TYPES and candidate_type == "tool_call"
            )
            if (
                candidate.ready
                and complementary
                and candidate.event.values.get("tool_call_id", "") == call_id
            ):
                return candidate
        return None


__all__ = ["OutputEventRectifier"]
