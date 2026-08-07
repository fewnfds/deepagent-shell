from __future__ import annotations

from collections.abc import Sequence
import json
import unicodedata
from typing import Literal, TYPE_CHECKING
from uuid import uuid4

from agent_shell.storage.history_retention import (
    HistoryRetentionStore,
    MAX_HISTORY_RETENTION_LIMIT,
)

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase
    from agent_shell.storage.media_outputs import MediaOutputStore


AgentRunStatus = Literal["completed", "failed", "client_disconnected"]


def _token_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _aggregate_token_usage(
    timelines: list[list[dict[str, object]]],
) -> dict[str, int | None]:
    usages: list[dict[str, object]] = []
    for timeline in timelines:
        for event in timeline:
            if event.get("kind") != "model_response":
                continue
            data = event.get("data")
            event_data = data if isinstance(data, dict) else {}
            usage = event_data.get("usage")
            usages.append(usage if isinstance(usage, dict) else {})

    input_total = 0
    reasoning_total = 0
    non_reasoning_total = 0
    input_complete = bool(usages)
    reasoning_complete = bool(usages)
    non_reasoning_complete = bool(usages)
    for usage in usages:
        input_tokens = _token_count(usage.get("input_tokens"))
        output_tokens = _token_count(usage.get("output_tokens"))
        output_details = usage.get("output_token_details")
        reasoning_tokens = _token_count(
            output_details.get("reasoning")
            if isinstance(output_details, dict)
            else None
        )
        if input_tokens is None:
            input_complete = False
        else:
            input_total += input_tokens
        if reasoning_tokens is None:
            reasoning_complete = False
        else:
            reasoning_total += reasoning_tokens
        if (
            output_tokens is None
            or reasoning_tokens is None
            or reasoning_tokens > output_tokens
        ):
            non_reasoning_complete = False
        else:
            non_reasoning_total += output_tokens - reasoning_tokens

    return {
        "input_tokens": input_total if input_complete else None,
        "non_reasoning_output_tokens": (
            non_reasoning_total if non_reasoning_complete else None
        ),
        "reasoning_output_tokens": (
            reasoning_total if reasoning_complete else None
        ),
    }


def _compact_text(value: object, limit: int = 96) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    normalized = " ".join(rendered.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit]}…"


def _normalized_search(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).casefold().strip()


def _timeline_event_summary(
    event: dict[str, object], index: int
) -> dict[str, object]:
    data = event.get("data")
    event_data = data if isinstance(data, dict) else {}
    kind = event.get("kind")
    summary_data: dict[str, object] = {}
    if kind == "model_request":
        for key in (
            "agent_type",
            "agent_name",
            "tool_call_id",
            "model_name",
            "message_count",
            "tool_count",
        ):
            default: object = 0 if key.endswith("count") else ""
            summary_data[key] = event_data.get(key, default)
    elif kind == "agent_input":
        for key in (
            "agent_type",
            "agent_name",
            "tool_call_id",
            "message_count",
        ):
            summary_data[key] = event_data.get(key, "" if key.endswith("id") else 0)
    elif kind == "model_response":
        for key in (
            "agent_name",
            "is_main_agent",
            "provider_finish_reason",
            "finish_reason_source",
            "finish_reason_category",
        ):
            summary_data[key] = event_data.get(key)
        usage = event_data.get("usage")
        if isinstance(usage, dict):
            summary_data["input_tokens"] = usage.get("input_tokens", 0)
            summary_data["output_tokens"] = usage.get("output_tokens", 0)
            summary_data["total_tokens"] = usage.get("total_tokens", 0)
    elif kind in {"tool_call", "tool_result", "tool_error"}:
        summary_data["tool_name"] = event_data.get("tool_name", "")
        for key in ("tool_call_id", "status", "error_code"):
            summary_data[key] = event_data.get(key, "")
    elif kind == "subagent":
        summary_data["phase"] = event_data.get("phase", "")
        summary_data["subagent_name"] = event_data.get("subagent_name", "")
    return {
        "step_id": f"event-{index}",
        "sequence": event.get("sequence", index + 1),
        "kind": kind,
        "timestamp": event.get("timestamp"),
        "data": summary_data,
    }


class AgentSessionStore:
    """One persisted row per OpenAI request; sessions are derived by session_id."""

    def __init__(
        self,
        database: SQLiteDatabase,
        history_retention: HistoryRetentionStore | None = None,
        media_outputs: MediaOutputStore | None = None,
    ) -> None:
        self._database = database
        self._history_retention = history_retention or HistoryRetentionStore(database)
        self._media_outputs = media_outputs
        with self._database.transaction() as connection:
            self._prune(
                connection,
                self._history_retention.get_limit_in(
                    connection, "agent_session_runs"
                ),
            )
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()

    @staticmethod
    def _prune(connection, retention_limit: int) -> None:
        connection.execute(
            "DELETE FROM agent_session_runs WHERE session_id NOT IN ("
            "SELECT session_id FROM agent_session_runs "
            "GROUP BY session_id "
            "ORDER BY MAX(started_at) DESC, MAX(rowid) DESC LIMIT ?)",
            (retention_limit,),
        )

    def history_retention(self) -> dict[str, int]:
        return {
            "retention_limit": self._history_retention.get_limit(
                "agent_session_runs"
            ),
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def set_history_retention(self, retention_limit: int) -> dict[str, int]:
        with self._database.transaction() as connection:
            self._history_retention.set_limit_in(
                connection, "agent_session_runs", retention_limit
            )
            self._prune(connection, retention_limit)
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()
        return {
            "retention_limit": retention_limit,
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def record_run(
        self,
        *,
        session_id: str,
        request_id: str,
        model: str,
        agent_name: str,
        started_at: str,
        finished_at: str,
        status: AgentRunStatus,
        input_messages: object,
        timeline: list[dict[str, object]],
        response_text: str,
        error_code: str | None,
        response_blocks: Sequence[dict[str, object]] = (),
        media_assets: Sequence[dict[str, object]] = (),
    ) -> None:
        item_id = str(uuid4())
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO agent_session_runs "
                "(id, session_id, request_id, model, agent_name, started_at, finished_at, "
                "status, error_code, input_messages_json, timeline_json, response_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    session_id,
                    request_id,
                    model,
                    agent_name,
                    started_at,
                    finished_at,
                    status,
                    error_code,
                    json.dumps(input_messages, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(timeline, ensure_ascii=False, separators=(",", ":")),
                    response_text,
                ),
            )
            connection.execute(
                "INSERT INTO agent_session_run_outputs "
                "(run_id, response_blocks_json, media_assets_json) "
                "VALUES (?, ?, ?)",
                (
                    item_id,
                    json.dumps(
                        response_blocks,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    json.dumps(
                        media_assets,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            self._prune(
                connection,
                self._history_retention.get_limit_in(
                    connection, "agent_session_runs"
                ),
            )
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()

    @staticmethod
    def _matching_session_summaries(
        connection, *, query: str, agent: str, status: str
    ) -> list[dict[str, object]]:
        rows = connection.execute(
            "SELECT session_id, request_id, model, agent_name, started_at, finished_at, "
            "status, error_code, "
            "(SELECT COUNT(*) FROM json_each(agent_session_runs.timeline_json) "
            "AS timeline_event WHERE json_extract(timeline_event.value, '$.kind') "
            "= 'model_request') AS model_call_count "
            "FROM agent_session_runs "
            "ORDER BY started_at ASC, rowid ASC"
        ).fetchall()
        grouped: dict[str, dict[str, object]] = {}
        for raw in rows:
            row = dict(raw)
            session_id = str(row["session_id"])
            summary = grouped.get(session_id)
            if summary is None:
                summary = {
                    "session_id": session_id,
                    "model": row["model"],
                    "agent_name": row["agent_name"],
                    "started_at": row["started_at"],
                    "updated_at": row["finished_at"] or row["started_at"],
                    "status": row["status"],
                    "error_code": row["error_code"],
                    "model_call_count": 0,
                    "_request_ids": [],
                }
                grouped[session_id] = summary
            summary["model_call_count"] = int(summary["model_call_count"]) + int(
                row["model_call_count"]
            )
            request_ids = summary["_request_ids"]
            if isinstance(request_ids, list):
                request_ids.append(str(row["request_id"]))
            summary["model"] = row["model"]
            summary["agent_name"] = row["agent_name"]
            summary["updated_at"] = row["finished_at"] or row["started_at"]
            summary["status"] = row["status"]
            summary["error_code"] = row["error_code"]
        needle = _normalized_search(query)
        agent_needle = _normalized_search(agent)
        items = []
        for item in grouped.values():
            if agent_needle and agent_needle not in _normalized_search(item["agent_name"]):
                continue
            if status and str(item["status"]) != status:
                continue
            haystack = " ".join(
                str(item[key])
                for key in ("session_id", "model", "agent_name", "status", "error_code")
            ) + " " + " ".join(str(value) for value in item["_request_ids"])
            if needle and needle not in _normalized_search(haystack):
                continue
            items.append(
                {key: value for key, value in item.items() if key != "_request_ids"}
            )
        items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
        return items

    def list_sessions(
        self,
        *,
        page: int,
        page_size: int,
        query: str,
        agent: str,
        status: str,
    ) -> dict[str, object]:
        with self._database.transaction() as connection:
            items = self._matching_session_summaries(
                connection,
                query=query,
                agent=agent,
                status=status,
            )
        total = len(items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def delete_matching_sessions(
        self, *, query: str, agent: str, status: str
    ) -> int:
        with self._database.transaction() as connection:
            items = self._matching_session_summaries(
                connection,
                query=query,
                agent=agent,
                status=status,
            )
            session_ids = [str(item["session_id"]) for item in items]
            if session_ids:
                connection.executemany(
                    "DELETE FROM agent_session_runs WHERE session_id = ?",
                    ((session_id,) for session_id in session_ids),
                )
                connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()
        return len(session_ids)

    def get_session(self, session_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT run.id, run.session_id, run.request_id, run.model, "
                "run.agent_name, run.started_at, run.finished_at, run.status, "
                "run.error_code, run.input_messages_json, run.timeline_json, "
                "run.response_text, "
                "COALESCE(output.response_blocks_json, '[]') AS response_blocks_json, "
                "COALESCE(output.media_assets_json, '[]') AS media_assets_json "
                "FROM agent_session_runs AS run "
                "LEFT JOIN agent_session_run_outputs AS output ON output.run_id = run.id "
                "WHERE run.session_id = ? ORDER BY run.started_at ASC, run.rowid ASC",
                (session_id,),
            ).fetchall()
        if not rows:
            return None
        runs = []
        timelines = []
        for raw in rows:
            item = dict(raw)
            item["input_messages"] = json.loads(item.pop("input_messages_json"))
            item["timeline"] = json.loads(item.pop("timeline_json"))
            item["response_blocks"] = json.loads(item.pop("response_blocks_json"))
            item["media_assets"] = json.loads(item.pop("media_assets_json"))
            timelines.append(
                [event for event in item["timeline"] if isinstance(event, dict)]
                if isinstance(item["timeline"], list)
                else []
            )
            runs.append(item)
        return {
            "session_id": session_id,
            "token_usage": _aggregate_token_usage(timelines),
            "runs": runs,
        }

    def get_session_timeline(self, session_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, session_id, request_id, model, agent_name, started_at, "
                "finished_at, status, error_code, "
                "json_array_length(input_messages_json) AS input_message_count, "
                "timeline_json, substr(response_text, 1, 97) AS response_summary "
                "FROM agent_session_runs WHERE session_id = ? "
                "ORDER BY started_at ASC, rowid ASC",
                (session_id,),
            ).fetchall()
        if not rows:
            return None
        timeline_runs = []
        timelines = []
        for raw in rows:
            run = dict(raw)
            raw_timeline = json.loads(run.pop("timeline_json"))
            timeline = (
                [event for event in raw_timeline if isinstance(event, dict)]
                if isinstance(raw_timeline, list)
                else []
            )
            timelines.append(timeline)
            run["response_summary"] = _compact_text(run["response_summary"])
            timeline_runs.append(
                run
                | {
                    "timeline": [
                        _timeline_event_summary(event, index)
                        for index, event in enumerate(timeline)
                        if isinstance(event, dict)
                    ],
                }
            )
        return {
            "session_id": session_id,
            "token_usage": _aggregate_token_usage(timelines),
            "runs": timeline_runs,
        }

    def get_session_step(
        self, session_id: str, run_id: str, step_id: str
    ) -> dict[str, object] | None:
        if step_id == "input":
            columns = "started_at, input_messages_json"
            event_index = None
        elif step_id == "output":
            columns = (
                "finished_at, status, error_code, response_text, "
                "COALESCE(output.response_blocks_json, '[]') AS response_blocks_json, "
                "COALESCE(output.media_assets_json, '[]') AS media_assets_json"
            )
            event_index = None
        elif step_id.startswith("event-"):
            try:
                event_index = int(step_id.removeprefix("event-"))
            except ValueError:
                return None
            if event_index < 0:
                return None
            columns = "json_extract(timeline_json, ?) AS event_json"
        else:
            return None
        parameters: tuple[object, ...] = (
            (f"$[{event_index}]", session_id, run_id)
            if event_index is not None
            else (session_id, run_id)
        )
        with self._database.transaction() as connection:
            raw = connection.execute(
                f"SELECT {columns} FROM agent_session_runs AS run "
                "LEFT JOIN agent_session_run_outputs AS output ON output.run_id = run.id "
                "WHERE run.session_id = ? AND run.id = ?",
                parameters,
            ).fetchone()
        if raw is None:
            return None
        run = dict(raw)
        if step_id == "input":
            return {
                "kind": "request_input",
                "timestamp": run.get("started_at"),
                "data": {"messages": json.loads(run["input_messages_json"])},
            }
        if step_id == "output":
            return {
                "kind": "request_output",
                "timestamp": run.get("finished_at"),
                "data": {
                    "status": run.get("status"),
                    "error_code": run.get("error_code"),
                    "response_text": run.get("response_text"),
                    "response_blocks": json.loads(run["response_blocks_json"]),
                    "media_assets": json.loads(run["media_assets_json"]),
                },
            }
        event_json = run.get("event_json")
        if not isinstance(event_json, str):
            return None
        event = json.loads(event_json)
        return event if isinstance(event, dict) else None

    def delete_session(self, session_id: str) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM agent_session_runs WHERE session_id = ?", (session_id,)
            )
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()
        return cursor.rowcount > 0
