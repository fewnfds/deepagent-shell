from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.security_events import SecurityEventLogger
from agent_shell.storage.event_feed import EventFeedStore
from agent_shell.storage.system_log_settings import MIB_BYTES, SystemLogSettingsStore


EVENT_DOWNLOAD_THRESHOLD_BYTES = 4 * 1024
EVENT_SUMMARY_MAX_CHARS = 240
EventSource = Literal["api_call", "interception", "system", "runtime"]
EventLevel = Literal["debug", "info", "warning", "error"]
EventDownloadView = Literal["raw", "debug"]

_SOURCE_RANK: dict[str, int] = {
    "api_call": 4,
    "interception": 3,
    "system": 2,
    "runtime": 1,
}


def _json_text(value: object, *, pretty: bool = False) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        **({"indent": 2} if pretty else {"separators": (",", ":")}),
    )


def _public_id(value: object) -> str:
    return hashlib.sha256(_json_text(value).encode("utf-8")).hexdigest()


def _summary(*values: object) -> str:
    text = " · ".join(str(value) for value in values if value not in (None, ""))
    return text if len(text) <= EVENT_SUMMARY_MAX_CHARS else text[:239] + "…"


def _detail_json(source: EventSource, entry: dict[str, object]) -> str:
    return _json_text({"source": source, "entry": entry}, pretty=True)


def _decoded_json(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _merged_chat_completion_stream(value: object) -> object:
    if not isinstance(value, str):
        return value
    chunks: list[dict[str, object]] = []
    unparsed_events: list[str] = []
    done = False
    for line in value.splitlines():
        if not line.startswith("data:"):
            if line.strip():
                unparsed_events.append(line)
            continue
        payload = line.removeprefix("data:").strip()
        if payload == "[DONE]":
            done = True
            continue
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            unparsed_events.append(payload)
            continue
        if isinstance(decoded, dict):
            chunks.append(decoded)
        else:
            unparsed_events.append(payload)

    if not chunks:
        return value

    content_parts: list[str] = []
    completion_id = ""
    model = ""
    created: object = None
    role = ""
    finish_reason: object = None
    usage: object = None
    error: object = None
    termination: object = None
    additional_deltas: list[dict[str, object]] = []
    for chunk in chunks:
        completion_id = completion_id or str(chunk.get("id") or "")
        model = model or str(chunk.get("model") or "")
        if created is None:
            created = chunk.get("created")
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice = choices[0]
            delta = choice.get("delta")
            if isinstance(delta, dict):
                if isinstance(delta.get("role"), str):
                    role = str(delta["role"])
                if isinstance(delta.get("content"), str):
                    content_parts.append(str(delta["content"]))
                extra_delta = {
                    key: item for key, item in delta.items()
                    if key not in {"role", "content"}
                }
                if extra_delta:
                    additional_deltas.append(extra_delta)
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
        if chunk.get("usage") is not None:
            usage = chunk["usage"]
        if chunk.get("error") is not None:
            error = chunk["error"]
        agent_shell = chunk.get("agent_shell")
        if isinstance(agent_shell, dict) and agent_shell.get("termination") is not None:
            termination = agent_shell["termination"]

    merged: dict[str, object] = {
        "object": "chat.completion.debug",
        "streamed": True,
        "chunk_count": len(chunks),
        "done": done,
        "id": completion_id,
        "created": created,
        "model": model,
        "role": role,
        "content": "".join(content_parts),
        "finish_reason": finish_reason,
        "usage": usage,
        "error": error,
        "termination": termination,
    }
    if additional_deltas:
        merged["additional_deltas"] = additional_deltas
    if unparsed_events:
        merged["unparsed_events"] = unparsed_events
    return merged


def _debug_api_entry(entry: dict[str, object]) -> dict[str, object]:
    debug = dict(entry)
    debug["request_body"] = _decoded_json(debug.get("request_body"))
    content_type = str(debug.get("response_content_type") or "")
    if content_type.partition(";")[0].strip().lower() == "text/event-stream":
        debug["response_body"] = _merged_chat_completion_stream(
            debug.get("response_body")
        )
    else:
        debug["response_body"] = _decoded_json(debug.get("response_body"))
    return debug


def _preview_scalar_fields(
    value: object,
    fields: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    preview: dict[str, object] = {}
    for field in fields:
        if field not in value:
            continue
        item = value[field]
        if item is None or isinstance(item, (str, int, float, bool)):
            preview[field] = item
    return preview


def _request_body_preview(value: object) -> dict[str, object]:
    preview = _preview_scalar_fields(
        value,
        (
            "model",
            "stream",
            "temperature",
            "top_p",
            "max_tokens",
            "max_completion_tokens",
            "n",
            "seed",
            "presence_penalty",
            "frequency_penalty",
            "service_tier",
            "reasoning_effort",
            "verbosity",
        ),
    )
    if isinstance(value, dict) and "messages" in value:
        messages = value["messages"]
        preview["messages_omitted"] = (
            len(messages) if isinstance(messages, list) else True
        )
    return preview


def _usage_preview(value: object) -> dict[str, object]:
    preview = _preview_scalar_fields(
        value,
        ("prompt_tokens", "completion_tokens", "total_tokens"),
    )
    if isinstance(value, dict):
        completion_details = _preview_scalar_fields(
            value.get("completion_tokens_details"),
            ("reasoning_tokens",),
        )
        if completion_details:
            preview["completion_tokens_details"] = completion_details
    return preview


def _termination_preview(value: object) -> dict[str, object]:
    return _preview_scalar_fields(
        value,
        ("status", "finish_reason", "category", "source", "reason"),
    )


def _response_body_preview(value: object) -> dict[str, object]:
    preview = _preview_scalar_fields(
        value,
        (
            "id",
            "object",
            "created",
            "model",
            "request_id",
            "streamed",
            "chunk_count",
            "done",
            "finish_reason",
        ),
    )
    if not isinstance(value, dict):
        return preview

    choices = value.get("choices")
    if isinstance(choices, list):
        preview["choice_count"] = len(choices)
        finish_reasons = [
            choice["finish_reason"]
            for choice in choices
            if isinstance(choice, dict)
            and isinstance(choice.get("finish_reason"), str)
        ]
        if finish_reasons:
            preview["finish_reasons"] = finish_reasons

    usage = _usage_preview(value.get("usage"))
    if usage:
        preview["usage"] = usage

    error = _preview_scalar_fields(
        value.get("error"),
        ("type", "param", "code", "message"),
    )
    if error:
        preview["error"] = error

    termination_value = value.get("termination")
    agent_shell = value.get("agent_shell")
    if isinstance(agent_shell, dict):
        termination_value = agent_shell.get("termination", termination_value)
    termination = _termination_preview(termination_value)
    if termination:
        preview["termination"] = termination
    return preview


def _api_preview_entry(entry: dict[str, object]) -> dict[str, object]:
    response_body: object = entry.get("response_body")
    content_type = str(entry.get("response_content_type") or "")
    if content_type.partition(";")[0].strip().lower() == "text/event-stream":
        response_body = _merged_chat_completion_stream(response_body)
    else:
        response_body = _decoded_json(response_body)
    return {
        "id": entry["id"],
        "request_id": entry["request_id"],
        "model": entry["model"],
        "agent_name": entry["agent_name"],
        "started_at": entry["started_at"],
        "finished_at": entry["finished_at"],
        "status": entry["status"],
        "request_body": _request_body_preview(
            _decoded_json(entry.get("request_body"))
        ),
        "response_body": _response_body_preview(response_body),
        "response_content_type": entry["response_content_type"],
        "http_status": entry["http_status"],
        "error_code": entry["error_code"],
    }


class EventFeedService:
    """Merge four existing observation sources without copying or migrating them."""

    def __init__(
        self,
        store: EventFeedStore,
        system_events: SecurityEventLogger,
        diagnostics: RuntimeDiagnostics,
        system_log_settings: SystemLogSettingsStore,
    ) -> None:
        self._store = store
        self._system_events = system_events
        self._diagnostics = diagnostics
        self._system_log_settings = system_log_settings

    def system_log_settings(self) -> dict[str, int]:
        return self._system_log_settings.snapshot()

    def set_system_log_max_size_mib(self, max_size_mib: int) -> dict[str, int]:
        settings = self._system_log_settings.set_max_size_mib(max_size_mib)
        self._system_events.set_max_bytes(max_size_mib * MIB_BYTES)
        self._system_events.emit(
            "configuration_updated",
            {
                "action": "updated",
                "entity": "system_log_settings",
                "entity_id": "system",
                "state": f"max_size_mib={max_size_mib}",
            },
        )
        return settings

    @staticmethod
    def _timestamp(value: object) -> datetime:
        timestamp = datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("event timestamp must include a timezone")
        return timestamp.astimezone(timezone.utc)

    @classmethod
    def _key(cls, item: dict[str, object]) -> tuple[datetime, int, str]:
        source = str(item["source"])
        return (
            cls._timestamp(item["occurred_at"]),
            _SOURCE_RANK[source],
            str(item["id"]),
        )

    @staticmethod
    def _api_statuses(levels: set[EventLevel]) -> tuple[str, ...]:
        mapping: tuple[tuple[EventLevel, str], ...] = (
            ("info", "completed"),
            ("error", "failed"),
            ("warning", "client_disconnected"),
        )
        return tuple(status for level, status in mapping if not levels or level in levels)

    @staticmethod
    def _api_item(row: dict[str, object]) -> dict[str, object]:
        status = str(row["status"])
        level = {
            "completed": "info",
            "failed": "error",
            "client_disconnected": "warning",
        }[status]
        content: str | None = None
        download_available = int(row["original_size_bytes"]) > EVENT_DOWNLOAD_THRESHOLD_BYTES
        if row["inline_request_body"] is not None:
            entry = {
                "id": row["id"],
                "request_id": row["request_id"],
                "model": row["model"],
                "agent_name": row["agent_name"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "status": status,
                "request_body": row["inline_request_body"],
                "response_body": row["inline_response_body"],
                "response_content_type": row["response_content_type"],
                "http_status": row["http_status"],
                "error_code": row["error_code"],
            }
            candidate = _detail_json("api_call", entry)
            if len(candidate.encode("utf-8")) <= EVENT_DOWNLOAD_THRESHOLD_BYTES:
                content = candidate
            else:
                download_available = True
        return {
            "id": row["id"],
            "source": "api_call",
            "occurred_at": row["started_at"],
            "level": level,
            "request_id": row["request_id"],
            "summary": _summary(
                row["agent_name"], status, row["http_status"], row["error_code"]
            ),
            "inline_content": content,
            "matched_in_content": bool(row["matched_in_content"])
            and content is None,
            "download_available": download_available,
        }

    @staticmethod
    def _interception_item(row: dict[str, object]) -> dict[str, object]:
        content: str | None = None
        download_available = int(row["original_size_bytes"]) > EVENT_DOWNLOAD_THRESHOLD_BYTES
        if row["inline_request_raw_json"] is not None:
            entry = {
                "id": row["id"],
                "name": row["name"],
                "intercepted_at": row["intercepted_at"],
                "request_id": row["request_id"],
                "model": row["model"],
                "agent_name": row["agent_name"],
                "request_raw_json": row["inline_request_raw_json"],
                "model_request_raw_json": row["inline_model_request_raw_json"],
            }
            candidate = _detail_json("interception", entry)
            if len(candidate.encode("utf-8")) <= EVENT_DOWNLOAD_THRESHOLD_BYTES:
                content = candidate
            else:
                download_available = True
        return {
            "id": row["id"],
            "source": "interception",
            "occurred_at": row["intercepted_at"],
            "level": "info",
            "request_id": row["request_id"],
            "summary": _summary(row["agent_name"], row["model"]),
            "inline_content": content,
            "matched_in_content": bool(row["matched_in_content"])
            and content is None,
            "download_available": download_available,
        }

    @staticmethod
    def _system_item(record: dict[str, object]) -> dict[str, object]:
        item_id = _public_id(record)
        content = _detail_json("system", record)
        size = len(content.encode("utf-8"))
        return {
            "id": item_id,
            "source": "system",
            "occurred_at": record["timestamp"],
            "level": record["level"],
            "request_id": record["request_id"],
            "summary": _summary(record["event"]),
            "inline_content": content if size <= EVENT_DOWNLOAD_THRESHOLD_BYTES else None,
            "matched_in_content": False,
            "download_available": size > EVENT_DOWNLOAD_THRESHOLD_BYTES,
        }

    @staticmethod
    def _runtime_item(record: dict[str, object]) -> dict[str, object]:
        item_id = _public_id(record)
        content = _detail_json("runtime", record)
        size = len(content.encode("utf-8"))
        detail = (
            _summary(record.get("message", ""))
            or _summary(record.get("code", ""))
            or "runtime diagnostic"
        )
        return {
            "id": item_id,
            "source": "runtime",
            "occurred_at": record["timestamp"],
            "level": record["level"],
            "request_id": record.get("request_id", ""),
            "summary": _summary(record.get("agent_name", ""), detail),
            "inline_content": content if size <= EVENT_DOWNLOAD_THRESHOLD_BYTES else None,
            "matched_in_content": False,
            "download_available": size > EVENT_DOWNLOAD_THRESHOLD_BYTES,
        }

    @classmethod
    def _public_items(
        cls,
        records: list[dict[str, object]],
        *,
        make_item: Callable[[dict[str, object]], dict[str, object]],
        levels: set[EventLevel],
        needle: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        for record in records:
            timestamp = cls._timestamp(record["timestamp"])
            if timestamp < started_at or timestamp > ended_at:
                continue
            if levels and record.get("level") not in levels:
                continue
            if needle and needle not in _json_text(record).casefold():
                continue
            item = make_item(record)
            if needle and item["inline_content"] is None:
                visible = {
                    key: value
                    for key, value in item.items()
                    if key not in {"id", "inline_content", "matched_in_content"}
                }
                item["matched_in_content"] = needle not in _json_text(visible).casefold()
            selected.append(item)
        return selected

    def list_events(
        self,
        *,
        page: int,
        page_size: int,
        started_at: datetime,
        ended_at: datetime,
        sources: set[EventSource],
        levels: set[EventLevel],
        query: str,
    ) -> dict[str, object]:
        selected_sources = sources or set(_SOURCE_RANK)
        items: list[dict[str, object]] = []
        started_at = started_at.astimezone(timezone.utc)
        ended_at = ended_at.astimezone(timezone.utc)
        started_iso = started_at.isoformat()
        ended_iso = ended_at.isoformat()

        if "api_call" in selected_sources:
            statuses = self._api_statuses(levels)
            if statuses:
                rows = self._store.list_api_calls(
                    query=query,
                    statuses=statuses,
                    started_at=started_iso,
                    ended_at=ended_iso,
                    inline_limit_bytes=EVENT_DOWNLOAD_THRESHOLD_BYTES,
                )
                items.extend(self._api_item(row) for row in rows)
        if "interception" in selected_sources and (not levels or "info" in levels):
            rows = self._store.list_interceptions(
                query=query,
                started_at=started_iso,
                ended_at=ended_iso,
                inline_limit_bytes=EVENT_DOWNLOAD_THRESHOLD_BYTES,
            )
            items.extend(self._interception_item(row) for row in rows)

        needle = query.casefold()
        if "system" in selected_sources:
            items.extend(
                self._public_items(
                    self._system_events.public_records(),
                    make_item=self._system_item,
                    levels=levels,
                    needle=needle,
                    started_at=started_at,
                    ended_at=ended_at,
                )
            )
        if "runtime" in selected_sources:
            records = [dict(value) for value in self._diagnostics.snapshot()["entries"]]
            items.extend(
                self._public_items(
                    records,
                    make_item=self._runtime_item,
                    levels=levels,
                    needle=needle,
                    started_at=started_at,
                    ended_at=ended_at,
                )
            )

        items.sort(key=self._key, reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return {
            "items": items[start:start + page_size],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    @staticmethod
    def _public_record_matches(
        record: dict[str, object],
        *,
        levels: set[EventLevel],
        needle: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> bool:
        timestamp = EventFeedService._timestamp(record["timestamp"])
        if timestamp < started_at or timestamp > ended_at:
            return False
        if levels and record.get("level") not in levels:
            return False
        return not needle or needle in _json_text(record).casefold()

    def delete_matching(
        self,
        *,
        started_at: datetime,
        ended_at: datetime,
        sources: set[EventSource],
        levels: set[EventLevel],
        query: str,
    ) -> dict[str, int]:
        selected_sources = sources or set(_SOURCE_RANK)
        started_at = started_at.astimezone(timezone.utc)
        ended_at = ended_at.astimezone(timezone.utc)
        started_iso = started_at.isoformat()
        ended_iso = ended_at.isoformat()
        deleted = 0
        if "api_call" in selected_sources:
            deleted += self._store.delete_api_calls(
                query=query,
                statuses=self._api_statuses(levels),
                started_at=started_iso,
                ended_at=ended_iso,
            )
        if "interception" in selected_sources and (not levels or "info" in levels):
            deleted += self._store.delete_interceptions(
                query=query,
                started_at=started_iso,
                ended_at=ended_iso,
            )

        needle = query.casefold()

        def matches(record: dict[str, object]) -> bool:
            return self._public_record_matches(
                record,
                levels=levels,
                needle=needle,
                started_at=started_at,
                ended_at=ended_at,
            )
        if "system" in selected_sources:
            deleted += self._system_events.delete_public_records(matches)
        if "runtime" in selected_sources:
            deleted += self._diagnostics.delete_entries(matches)
        return {"deleted": deleted}

    def _system_record(self, item_id: str) -> dict[str, object] | None:
        return next(
            (
                record
                for record in self._system_events.public_records()
                if _public_id(record) == item_id
            ),
            None,
        )

    def _runtime_record(self, item_id: str) -> dict[str, object] | None:
        return next(
            (
                dict(record)
                for record in self._diagnostics.snapshot()["entries"]
                if _public_id(record) == item_id
            ),
            None,
        )

    def download(
        self,
        source: EventSource,
        item_id: str,
        view: EventDownloadView = "raw",
    ) -> tuple[bytes, str] | None:
        if source == "api_call":
            entry = self._store.get_api_call(item_id)
            timestamp_key = "started_at"
        elif source == "interception":
            entry = self._store.get_interception(item_id)
            timestamp_key = "intercepted_at"
        elif source == "system":
            entry = self._system_record(item_id)
            timestamp_key = "timestamp"
        else:
            entry = self._runtime_record(item_id)
            timestamp_key = "timestamp"
        if entry is None:
            return None
        if view == "debug" and source == "api_call":
            entry = _debug_api_entry(entry)
            entry["runtime_diagnostics"] = self._diagnostics.entries_for_request(
                str(entry.get("request_id") or "")
            )
        content = (_detail_json(source, entry) + "\n").encode("utf-8")
        timestamp = datetime.fromisoformat(str(entry[timestamp_key])).astimezone(timezone.utc)
        stamp = timestamp.strftime("%Y%m%dT%H%M%S%f")[:-3] + "Z"
        suffix = "-debug" if view == "debug" and source == "api_call" else ""
        filename = f"agent-shell-event-{source}-{stamp}-{item_id[:8]}{suffix}.json"
        return content, filename

    def api_preview(self, item_id: str) -> str | None:
        entry = self._store.get_api_call(item_id)
        if entry is None:
            return None
        return _detail_json("api_call", _api_preview_entry(entry))
