from __future__ import annotations

from collections.abc import Callable
import sqlite3

from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.history_retention import (
    HistoryRetentionStore,
    MAX_HISTORY_RETENTION_LIMIT,
)


class RuntimeDiagnosticStore:
    """Persist the structured, already-sanitized Agent runtime log."""

    def __init__(
        self,
        database: SQLiteDatabase,
        history_retention: HistoryRetentionStore,
    ) -> None:
        self._database = database
        self._history_retention = history_retention
        with self._database.transaction() as connection:
            self._prune(
                connection,
                self._history_retention.get_limit_in(connection, "runtime_log"),
            )
            connection.commit()

    @staticmethod
    def _prune(connection: sqlite3.Connection, retention_limit: int) -> None:
        connection.execute(
            "DELETE FROM runtime_diagnostics WHERE sequence NOT IN ("
            "SELECT sequence FROM runtime_diagnostics "
            "ORDER BY sequence DESC LIMIT ?)",
            (retention_limit,),
        )

    @staticmethod
    def _entry(row: sqlite3.Row) -> dict[str, object]:
        return {
            "sequence": int(row["sequence"]),
            "timestamp": row["timestamp"],
            "level": row["level"],
            "request_id": row["request_id"],
            "model": row["model"],
            "agent_name": row["agent_name"],
            "code": row["code"],
            "exception_type": row["exception_type"],
            "message": row["message"],
        }

    def add(
        self,
        *,
        timestamp: str,
        level: str,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
        exception_type: str,
        message: str,
    ) -> dict[str, object]:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO runtime_diagnostics "
                "(timestamp, level, request_id, model, agent_name, code, "
                "exception_type, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    timestamp,
                    level,
                    request_id,
                    model,
                    agent_name,
                    code,
                    exception_type,
                    message,
                ),
            )
            self._prune(
                connection,
                self._history_retention.get_limit_in(connection, "runtime_log"),
            )
            connection.commit()
        return {
            "sequence": int(cursor.lastrowid),
            "timestamp": timestamp,
            "level": level,
            "request_id": request_id,
            "model": model,
            "agent_name": agent_name,
            "code": code,
            "exception_type": exception_type,
            "message": message,
        }

    def entries(self, *, request_id: str | None = None) -> list[dict[str, object]]:
        where = " WHERE request_id = ?" if request_id is not None else ""
        parameters = (request_id,) if request_id is not None else ()
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT sequence, timestamp, level, request_id, model, agent_name, "
                "code, exception_type, message FROM runtime_diagnostics"
                + where
                + " ORDER BY sequence ASC",
                parameters,
            ).fetchall()
        return [self._entry(row) for row in rows]

    def delete_entries(
        self,
        predicate: Callable[[dict[str, object]], bool],
    ) -> int:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT sequence, timestamp, level, request_id, model, agent_name, "
                "code, exception_type, message FROM runtime_diagnostics"
            ).fetchall()
            sequences = [
                int(row["sequence"])
                for row in rows
                if predicate(self._entry(row))
            ]
            if sequences:
                connection.executemany(
                    "DELETE FROM runtime_diagnostics WHERE sequence = ?",
                    ((sequence,) for sequence in sequences),
                )
                connection.commit()
        return len(sequences)

    def retention(self) -> dict[str, int]:
        return {
            "retention_limit": self._history_retention.get_limit("runtime_log"),
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def set_retention(self, retention_limit: int) -> dict[str, int]:
        with self._database.transaction() as connection:
            self._history_retention.set_limit_in(
                connection, "runtime_log", retention_limit
            )
            self._prune(connection, retention_limit)
            connection.commit()
        return {
            "retention_limit": retention_limit,
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }
