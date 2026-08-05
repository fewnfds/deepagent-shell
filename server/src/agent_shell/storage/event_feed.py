from __future__ import annotations

import json

from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.media_outputs import MediaOutputStore


def _escaped_needle(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _time_window(
    *,
    timestamp_column: str,
    started_at: str,
    ended_at: str,
) -> tuple[str, list[object]]:
    parameters: list[object] = [started_at, ended_at]
    return (
        f"julianday({timestamp_column}) >= julianday(?) AND "
        f"julianday({timestamp_column}) <= julianday(?)",
        parameters,
    )


class EventFeedStore:
    """Query and delete the two SQLite-backed event sources."""

    def __init__(
        self,
        database: SQLiteDatabase,
        media_outputs: MediaOutputStore | None = None,
    ) -> None:
        self._database = database
        self._media_outputs = media_outputs

    def list_api_calls(
        self,
        *,
        query: str,
        statuses: tuple[str, ...],
        started_at: str,
        ended_at: str,
        inline_limit_bytes: int,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        parameters: list[object] = []
        window, window_parameters = _time_window(
            timestamp_column="started_at",
            started_at=started_at,
            ended_at=ended_at,
        )
        clauses.append(window)
        parameters.extend(window_parameters)
        placeholders = ", ".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        parameters.extend(statuses)
        needle = ""
        if query:
            needle = _escaped_needle(query)
            searchable = (
                "request_id",
                "model",
                "agent_name",
                "status",
                "request_body",
                "COALESCE(response_body, '')",
                "COALESCE(error_code, '')",
            )
            clauses.append(
                "(" + " OR ".join(
                    f"{column} LIKE ? ESCAPE '\\'" for column in searchable
                ) + ")"
            )
            parameters.extend([needle] * len(searchable))
        where = " WHERE " + " AND ".join(clauses)
        size_sql = (
            "length(CAST(request_body AS BLOB)) + "
            "COALESCE(length(CAST(response_body AS BLOB)), 0)"
        )
        select_parameters: list[object] = [inline_limit_bytes, inline_limit_bytes]
        body_match_sql = "0 AS matched_in_content"
        if needle:
            body_match_sql = (
                "CASE WHEN request_body LIKE ? ESCAPE '\\' OR "
                "COALESCE(response_body, '') LIKE ? ESCAPE '\\' "
                "THEN 1 ELSE 0 END AS matched_in_content"
            )
            select_parameters.extend([needle, needle])
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, request_id, model, agent_name, started_at, finished_at, "
                "status, response_content_type, http_status, error_code, "
                f"{size_sql} AS original_size_bytes, "
                f"CASE WHEN {size_sql} <= ? THEN request_body ELSE NULL END "
                "AS inline_request_body, "
                f"CASE WHEN {size_sql} <= ? THEN response_body ELSE NULL END "
                "AS inline_response_body, "
                f"{body_match_sql} "
                "FROM api_message_history" + where +
                " ORDER BY started_at DESC, id DESC",
                [*select_parameters, *parameters],
            ).fetchall()
        return [dict(row) for row in rows]

    def list_interceptions(
        self,
        *,
        query: str,
        started_at: str,
        ended_at: str,
        inline_limit_bytes: int,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        parameters: list[object] = []
        window, window_parameters = _time_window(
            timestamp_column="intercepted_at",
            started_at=started_at,
            ended_at=ended_at,
        )
        clauses.append(window)
        parameters.extend(window_parameters)
        needle = ""
        if query:
            needle = _escaped_needle(query)
            searchable = (
                "name",
                "intercepted_at",
                "request_id",
                "model",
                "agent_name",
                "request_raw_json",
                "model_request_raw_json",
            )
            clauses.append(
                "(" + " OR ".join(
                    f"{column} LIKE ? ESCAPE '\\'" for column in searchable
                ) + ")"
            )
            parameters.extend([needle] * len(searchable))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        size_sql = (
            "length(CAST(request_raw_json AS BLOB)) + "
            "length(CAST(model_request_raw_json AS BLOB))"
        )
        select_parameters: list[object] = [inline_limit_bytes, inline_limit_bytes]
        body_match_sql = "0 AS matched_in_content"
        if needle:
            body_match_sql = (
                "CASE WHEN request_raw_json LIKE ? ESCAPE '\\' OR "
                "model_request_raw_json LIKE ? ESCAPE '\\' "
                "THEN 1 ELSE 0 END AS matched_in_content"
            )
            select_parameters.extend([needle, needle])
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, name, intercepted_at, request_id, model, agent_name, "
                f"{size_sql} AS original_size_bytes, "
                f"CASE WHEN {size_sql} <= ? THEN request_raw_json ELSE NULL END "
                "AS inline_request_raw_json, "
                f"CASE WHEN {size_sql} <= ? THEN model_request_raw_json ELSE NULL END "
                "AS inline_model_request_raw_json, "
                f"{body_match_sql} "
                "FROM interception_test_records" + where +
                " ORDER BY intercepted_at DESC, id DESC",
                [*select_parameters, *parameters],
            ).fetchall()
        return [dict(row) for row in rows]

    def get_api_call(self, item_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, request_id, model, agent_name, started_at, finished_at, "
                "status, request_body, response_body, response_content_type, "
                "http_status, error_code, response_blocks_json, media_assets_json "
                "FROM api_message_history WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["response_blocks"] = json.loads(item.pop("response_blocks_json"))
        item["media_assets"] = json.loads(item.pop("media_assets_json"))
        return item

    def get_interception(self, item_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, name, intercepted_at, request_id, model, agent_name, "
                "request_raw_json, model_request_raw_json "
                "FROM interception_test_records WHERE id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_api_calls(
        self,
        *,
        query: str,
        statuses: tuple[str, ...],
        started_at: str,
        ended_at: str,
    ) -> int:
        if not statuses:
            return 0
        placeholders = ", ".join("?" for _ in statuses)
        window, parameters = _time_window(
            timestamp_column="started_at",
            started_at=started_at,
            ended_at=ended_at,
        )
        clauses = [window, f"status IN ({placeholders})"]
        parameters.extend(statuses)
        if query:
            needle = _escaped_needle(query)
            searchable = (
                "request_id",
                "model",
                "agent_name",
                "status",
                "request_body",
                "COALESCE(response_body, '')",
                "COALESCE(error_code, '')",
            )
            clauses.append(
                "(" + " OR ".join(
                    f"{column} LIKE ? ESCAPE '\\'" for column in searchable
                ) + ")"
            )
            parameters.extend([needle] * len(searchable))
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM api_message_history WHERE " + " AND ".join(clauses),
                parameters,
            )
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()
        return cursor.rowcount

    def delete_interceptions(
        self,
        *,
        query: str,
        started_at: str,
        ended_at: str,
    ) -> int:
        window, parameters = _time_window(
            timestamp_column="intercepted_at",
            started_at=started_at,
            ended_at=ended_at,
        )
        clauses = [window]
        if query:
            needle = _escaped_needle(query)
            searchable = (
                "name",
                "intercepted_at",
                "request_id",
                "model",
                "agent_name",
                "request_raw_json",
                "model_request_raw_json",
            )
            clauses.append(
                "(" + " OR ".join(
                    f"{column} LIKE ? ESCAPE '\\'" for column in searchable
                ) + ")"
            )
            parameters.extend([needle] * len(searchable))
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM interception_test_records WHERE " + " AND ".join(clauses),
                parameters,
            )
        return cursor.rowcount
