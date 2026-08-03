from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


WORKFLOW_TABLES = {
    "hook-workflow": "hook_workflows",
    "lifecycle-workflow": "lifecycle_workflows",
}


class AutomationStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _table(workflow_type: str) -> str:
        try:
            return WORKFLOW_TABLES[workflow_type]
        except KeyError as exc:
            raise ValueError(f"unsupported workflow type: {workflow_type}") from exc

    @staticmethod
    def _from_row(row: sqlite3.Row) -> dict:
        item = json.loads(row["payload"])
        item["id"] = row["id"]
        item["name"] = row["name"]
        return item

    def list_items(self, workflow_type: str) -> list[dict]:
        table = self._table(workflow_type)
        with self._database.transaction() as connection:
            rows = connection.execute(
                f"SELECT id, name, payload FROM {table} "
                "ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_item(self, workflow_type: str, item_id: str) -> dict | None:
        table = self._table(workflow_type)
        with self._database.transaction() as connection:
            row = connection.execute(
                f"SELECT id, name, payload FROM {table} WHERE id = ?", (item_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def save_item(self, workflow_type: str, item_id: str, data: dict) -> None:
        table = self._table(workflow_type)
        name = data["name"]
        payload = json.dumps(
            {key: value for key, value in data.items() if key != "name"},
            ensure_ascii=False,
        )
        with self._database.transaction() as connection:
            existing = connection.execute(
                f"SELECT 1 FROM {table} WHERE id = ?", (item_id,)
            ).fetchone()
            duplicate = connection.execute(
                f"SELECT id FROM {table} WHERE name = ? AND id != ?",
                (name, item_id),
            ).fetchone()
            if duplicate:
                raise ValueError(f"名称「{name}」已存在")
            connection.execute(
                f"INSERT INTO {table} (id, name, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, "
                "payload = excluded.payload",
                (item_id, name, payload),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity=workflow_type,
            entity_id=item_id,
        )

    def delete_items(self, workflow_type: str, item_ids: list[str]) -> int:
        table = self._table(workflow_type)
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return 0
        placeholders = ", ".join("?" for _ in unique_ids)
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = {
                str(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM {table} WHERE id IN ({placeholders})",
                    unique_ids,
                ).fetchall()
            }
            connection.execute(
                f"DELETE FROM {table} WHERE id IN ({placeholders})", unique_ids
            )
            connection.commit()
        for item_id in unique_ids:
            if item_id in existing:
                emit_configuration_events(
                    self._events,
                    action="deleted",
                    entity=workflow_type,
                    entity_id=item_id,
                )
        return len(existing)

    def delete_item(self, workflow_type: str, item_id: str) -> bool:
        return self.delete_items(workflow_type, [item_id]) == 1

