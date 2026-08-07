from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class GraphRunStore:
    """Small management index for runs; LangGraph checkpointer owns snapshots."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "graph_id": row["graph_id"], "entry_script_id": row["entry_script_id"],
            "thread_id": row["thread_id"], "status": row["status"],
            "input": json.loads(row["input_json"]), "state": json.loads(row["state_json"]),
            "error_code": row["error_code"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def create(self, *, run_id: str, graph_id: str, thread_id: str, entry_script_id: str | None, input_value: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO graph_runs (id, graph_id, entry_script_id, thread_id, status, input_json, state_json, error_code, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, '{}', NULL, ?, ?)",
                (run_id, graph_id, entry_script_id, thread_id, json.dumps(input_value, ensure_ascii=False), now, now),
            )
            connection.commit()
        return self.get(run_id) or {}

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute("SELECT * FROM graph_runs WHERE id = ?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, graph_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM graph_runs"
        params: tuple[Any, ...] = ()
        if graph_id:
            query += " WHERE graph_id = ?"
            params = (graph_id,)
        query += " ORDER BY updated_at DESC"
        with self._database.transaction() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row(row) for row in rows]

    def update(self, run_id: str, *, status: str | None = None, state: dict[str, Any] | None = None, error_code: str | None = None) -> dict[str, Any] | None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?"); values.append(status)
        if state is not None:
            fields.append("state_json = ?"); values.append(json.dumps(state, ensure_ascii=False, default=str))
        if error_code is not None:
            fields.append("error_code = ?"); values.append(error_code)
        values.append(run_id)
        with self._database.transaction() as connection:
            connection.execute(f"UPDATE graph_runs SET {', '.join(fields)} WHERE id = ?", values)
            connection.commit()
        return self.get(run_id)
