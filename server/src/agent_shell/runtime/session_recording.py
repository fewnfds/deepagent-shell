from __future__ import annotations

from datetime import datetime, timezone
import threading

from agent_shell.runtime.model_response import ModelResponse
from agent_shell.runtime.output_stream import OutputEvent


_RECORDED_EVENT_TYPES = frozenset(
    {
        "lifecycle",
        "tool_call",
        "tool_result",
        "tool_error",
        "subagent",
    }
)


class AgentRunCapture:
    """Request-local ordered capture shared by ModelRequest and v3 event observers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._timeline: list[dict[str, object]] = []

    def model_request(self, payload: dict[str, object]) -> None:
        model = payload.get("model")
        model_name = model.get("name", "") if isinstance(model, dict) else ""
        messages = payload.get("messages")
        tools = payload.get("tools")
        self._append(
            "model_request",
            {
                "agent_type": payload.get("agent_type", ""),
                "agent_name": payload.get("agent_name", ""),
                "tool_call_id": payload.get("tool_call_id", ""),
                "model_name": model_name,
                "message_count": len(messages) if isinstance(messages, list) else 0,
                "tool_count": len(tools) if isinstance(tools, list) else 0,
            },
        )

    def agent_input(self, payload: dict[str, object]) -> None:
        safe = {
            key: payload.get(key)
            for key in (
                "agent_type",
                "agent_name",
                "owner_id",
                "invocation_id",
                "parent_invocation_id",
                "tool_call_id",
                "message_count",
            )
        }
        self._append("agent_input", safe)

    def model_response(self, response: ModelResponse) -> None:
        self._append(
            "model_response",
            {
                "namespace": response.namespace,
                "agent_name": response.agent_name,
                "node": response.node,
                "run_id": response.run_id,
                "message_id": response.message_id,
                "is_primary": response.is_primary,
                "provider_finish_reason": response.provider_finish_reason,
                "finish_reason_source": response.finish_reason_source,
                "finish_reason_category": response.timeline_data()[
                    "finish_reason_category"
                ],
                "usage": self._safe_usage(response.usage),
                "stream_diagnostics": self._safe_stream_diagnostics(
                    response.stream_diagnostics
                ),
            },
            timestamp=response.timestamp,
        )

    def output_event(self, event: OutputEvent) -> None:
        if event.event_type not in _RECORDED_EVENT_TYPES:
            return
        allowed_values = {
            "lifecycle": ("status", "finish_reason", "error_code"),
            "tool_call": ("tool_name", "tool_call_id", "status"),
            "tool_result": ("tool_name", "tool_call_id", "status"),
            "tool_error": ("tool_name", "tool_call_id", "status", "error_code"),
            "subagent": ("subagent_name", "tool_call_id", "status"),
        }
        self._append(
            event.event_type,
            {
                "phase": event.phase,
                "namespace": event.namespace,
                "agent_name": event.agent_name,
                "node": event.node,
                **{
                    key: event.values.get(key, "")
                    for key in allowed_values[event.event_type]
                },
            },
        )

    @staticmethod
    def _safe_usage(usage: dict[str, object]) -> dict[str, object]:
        safe: dict[str, object] = {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is int and value >= 0:
                safe[key] = value
        detail_fields = {
            "input_token_details": ("audio", "cache_creation", "cache_read"),
            "output_token_details": ("audio", "reasoning"),
        }
        for key, allowed in detail_fields.items():
            value = usage.get(key)
            if not isinstance(value, dict):
                continue
            details = {
                field: value[field]
                for field in allowed
                if type(value.get(field)) is int and value[field] >= 0
            }
            if details:
                safe[key] = details
        return safe

    @staticmethod
    def _safe_stream_diagnostics(value: dict[str, object]) -> dict[str, int]:
        fields = (
            "content_block_count",
            "delta_block_count",
            "snapshot_mismatch_count",
            "block_type_mismatch_count",
            "incomplete_block_count",
        )
        return {
            key: value[key]
            for key in fields
            if type(value.get(key)) is int and value[key] >= 0
        }

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [dict(item) for item in self._timeline]

    def _append(
        self,
        kind: str,
        payload: dict[str, object],
        *,
        timestamp: str | None = None,
    ) -> None:
        with self._lock:
            self._sequence += 1
            self._timeline.append(
                {
                    "sequence": self._sequence,
                    "timestamp": timestamp
                    or datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "kind": kind,
                    "data": payload,
                }
            )
