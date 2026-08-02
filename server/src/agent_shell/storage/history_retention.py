from __future__ import annotations

import sqlite3

from agent_shell.storage.database import SQLiteDatabase


DEFAULT_HISTORY_RETENTION_LIMIT = 20
MAX_HISTORY_RETENTION_LIMIT = 10_000
HISTORY_TYPES = frozenset(
    {"api_history", "interception_history", "agent_session_runs", "runtime_log"}
)


class HistoryRetentionStore:
    """Persist limits for the concrete retained history sources."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    @staticmethod
    def _type(history_type: str) -> str:
        if history_type not in HISTORY_TYPES:
            raise ValueError(f"unsupported history type: {history_type}")
        return history_type

    def get_limit(self, history_type: str) -> int:
        history_type = self._type(history_type)
        with self._database.transaction() as connection:
            return self.get_limit_in(connection, history_type)

    def get_limit_in(
        self, connection: sqlite3.Connection, history_type: str
    ) -> int:
        history_type = self._type(history_type)
        row = connection.execute(
            "SELECT retention_limit FROM history_retention_settings "
            "WHERE history_type = ?",
            (history_type,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"history retention setting is unavailable: {history_type}")
        return int(row["retention_limit"])

    def set_limit_in(
        self,
        connection: sqlite3.Connection,
        history_type: str,
        retention_limit: int,
    ) -> None:
        history_type = self._type(history_type)
        if not 1 <= retention_limit <= MAX_HISTORY_RETENTION_LIMIT:
            raise ValueError("history retention limit is out of range")
        connection.execute(
            "UPDATE history_retention_settings SET retention_limit = ? "
            "WHERE history_type = ?",
            (retention_limit, history_type),
        )

    def set_limit(self, history_type: str, retention_limit: int) -> int:
        with self._database.transaction() as connection:
            self.set_limit_in(connection, history_type, retention_limit)
            connection.commit()
        return retention_limit
