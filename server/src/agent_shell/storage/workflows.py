from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


class WorkflowStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _from_row(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "description": str(row["description"]),
            "main_agent_id": str(row["main_agent_id"]),
            "main_agent_name": str(row["main_agent_name"]),
            "enabled": bool(row["enabled"]),
        }

    @staticmethod
    def _select(where: str = "") -> str:
        return (
            "SELECT w.id, w.name, w.description, w.main_agent_id, w.enabled, "
            "m.name AS main_agent_name FROM workflows AS w "
            "JOIN main_agents AS m ON m.id = w.main_agent_id "
            f"{where}"
        )

    def list_items(self, *, enabled_only: bool = False) -> list[dict]:
        where = "WHERE w.enabled = 1 " if enabled_only else ""
        with self._database.transaction() as connection:
            rows = connection.execute(
                self._select(where) + "ORDER BY w.name COLLATE NOCASE, w.id"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_item(self, item_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE w.id = ?"), (item_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_item_by_name(self, name: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE w.name = ?"), (name,)
            ).fetchone()
        return self._from_row(row) if row else None

    def save_item(self, item_id: str, data: dict) -> None:
        with self._database.transaction() as connection:
            existing = connection.execute(
                "SELECT 1 FROM workflows WHERE id = ?", (item_id,)
            ).fetchone()
            duplicate = connection.execute(
                "SELECT id FROM workflows WHERE name = ? AND id != ?",
                (data["name"], item_id),
            ).fetchone()
            if duplicate:
                raise ValueError("workflow name already exists")
            if connection.execute(
                "SELECT 1 FROM main_agents WHERE id = ?", (data["main_agent_id"],)
            ).fetchone() is None:
                raise LookupError("main agent does not exist")
            connection.execute(
                "INSERT INTO workflows "
                "(id, name, description, main_agent_id, enabled) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name = excluded.name, description = excluded.description, "
                "main_agent_id = excluded.main_agent_id, enabled = excluded.enabled",
                (
                    item_id,
                    data["name"],
                    data["description"],
                    data["main_agent_id"],
                    int(data["enabled"]),
                ),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="workflow",
            entity_id=item_id,
        )

    def delete_items(self, item_ids: list[str]) -> int:
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return 0
        placeholders = ", ".join("?" for _ in unique_ids)
        with self._database.transaction() as connection:
            existing = {
                str(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM workflows WHERE id IN ({placeholders})",
                    unique_ids,
                ).fetchall()
            }
            connection.execute(
                f"DELETE FROM workflows WHERE id IN ({placeholders})", unique_ids
            )
            connection.commit()
        for item_id in existing:
            emit_configuration_events(
                self._events,
                action="deleted",
                entity="workflow",
                entity_id=item_id,
            )
        return len(existing)

    def delete_item(self, item_id: str) -> bool:
        return self.delete_items([item_id]) == 1

    def referencing_main_agent(self, main_agent_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE w.main_agent_id = ? ORDER BY w.name COLLATE NOCASE LIMIT 1"),
                (main_agent_id,),
            ).fetchone()
        return self._from_row(row) if row else None

