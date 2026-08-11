from __future__ import annotations

from agent_shell.storage.database import SQLiteDatabase


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
    """Query and delete the interception-test event source."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

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
        where = " WHERE " + " AND ".join(clauses)
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

    def get_interception(self, item_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, name, intercepted_at, request_id, model, agent_name, "
                "request_raw_json, model_request_raw_json "
                "FROM interception_test_records WHERE id = ?",
                (item_id,),
            ).fetchone()
        return dict(row) if row else None

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
