from __future__ import annotations

import json
import sqlite3

from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.history_retention import (
    HistoryRetentionStore,
    MAX_HISTORY_RETENTION_LIMIT,
)


class WorkflowRunStore:
    """Persist the bounded local index for Workflow Debug runs."""

    def __init__(
        self,
        database: SQLiteDatabase,
        history_retention: HistoryRetentionStore,
    ) -> None:
        self._database = database
        self._history_retention = history_retention

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, object]:
        return {
            "thread_id": row["thread_id"],
            "run_id": row["run_id"],
            "request_id": row["request_id"],
            "workflow_id": row["workflow_id"],
            "workflow_name": row["workflow_name"],
            "messages_sha": row["messages_sha"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error_code": row["error_code"],
            "langsmith_project": row["langsmith_project"],
            "tracing_enabled": bool(row["tracing_enabled"]),
            "run_tree": json.loads(row["run_tree_json"]),
        }

    def begin(self, record: dict[str, object]) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO workflow_runs "
                "(thread_id, run_id, request_id, workflow_id, workflow_name, "
                "messages_sha, status, started_at, finished_at, error_code, "
                "langsmith_project, tracing_enabled, run_tree_json) "
                "VALUES (?, ?, ?, ?, ?, ?, 'running', ?, NULL, '', ?, ?, ?)",
                (
                    record["thread_id"],
                    record["run_id"],
                    record["request_id"],
                    record["workflow_id"],
                    record["workflow_name"],
                    record["messages_sha"],
                    record["started_at"],
                    record["langsmith_project"],
                    int(bool(record["tracing_enabled"])),
                    json.dumps(record["run_tree"], ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def cancel_running(self, *, finished_at: str) -> int:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT thread_id, run_tree_json FROM workflow_runs "
                "WHERE status = 'running'"
            ).fetchall()
            for row in rows:
                run_tree = json.loads(row["run_tree_json"])
                for node in run_tree:
                    if node.get("status") == "running":
                        node["status"] = "cancelled"
                        node["finished_at"] = finished_at
                connection.execute(
                    "UPDATE workflow_runs SET status = 'cancelled', "
                    "finished_at = ?, error_code = 'service_restarted', "
                    "run_tree_json = ? WHERE thread_id = ?",
                    (
                        finished_at,
                        json.dumps(
                            run_tree,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        row["thread_id"],
                    ),
                )
        return len(rows)

    def finish(
        self,
        *,
        thread_id: str,
        status: str,
        finished_at: str,
        error_code: str,
        run_tree: list[dict[str, object]],
    ) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE workflow_runs SET status = ?, finished_at = ?, "
                "error_code = ?, run_tree_json = ? WHERE thread_id = ?",
                (
                    status,
                    finished_at,
                    error_code,
                    json.dumps(run_tree, ensure_ascii=False, separators=(",", ":")),
                    thread_id,
                ),
            )
            retention = self._history_retention.get_limit_in(
                connection, "workflow_debug_history"
            )
            removed = connection.execute(
                "SELECT thread_id FROM workflow_runs "
                "WHERE status != 'running' AND thread_id NOT IN ("
                "SELECT thread_id FROM workflow_runs "
                "WHERE status != 'running' "
                "ORDER BY started_at DESC, thread_id DESC LIMIT ?)",
                (retention,),
            ).fetchall()
            removed_ids = tuple(str(row["thread_id"]) for row in removed)
            if removed_ids:
                connection.executemany(
                    "DELETE FROM workflow_runs WHERE thread_id = ?",
                    ((item,) for item in removed_ids),
                )

    def list(self, *, limit: int) -> list[dict[str, object]]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM workflow_runs "
                "ORDER BY started_at DESC, thread_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, thread_id: str) -> dict[str, object] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def delete(self, thread_id: str) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_runs WHERE thread_id = ?",
                (thread_id,),
            )
        return cursor.rowcount > 0

    def retention(self) -> dict[str, int]:
        return {
            "retention_limit": self._history_retention.get_limit("workflow_debug_history"),
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def set_retention(self, retention_limit: int) -> dict[str, int]:
        with self._database.transaction() as connection:
            self._history_retention.set_limit_in(
                connection, "workflow_debug_history", retention_limit
            )
            connection.execute(
                "DELETE FROM workflow_runs WHERE status != 'running' AND thread_id NOT IN ("
                "SELECT thread_id FROM workflow_runs WHERE status != 'running' "
                "ORDER BY started_at DESC, thread_id DESC LIMIT ?)",
                (retention_limit,),
            )
            connection.commit()
        return self.retention()


__all__ = ["WorkflowRunStore"]
