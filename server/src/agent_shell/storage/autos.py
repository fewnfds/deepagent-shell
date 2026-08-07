from __future__ import annotations

import json
import sqlite3
from typing import Any, TYPE_CHECKING

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.auto.contracts import AutoDefinition

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


class AutoStore:
    def __init__(self, database: SQLiteDatabase, event_logger: SecurityEventLogger | None = None) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        payload["id"] = row["id"]
        payload["revision"] = row["revision"]
        return payload

    def list_items(self) -> list[dict[str, Any]]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, payload, revision FROM auto_roots "
                "ORDER BY json_extract(payload, '$.public_id') COLLATE NOCASE, id"
            ).fetchall()
        return [self._row(row) for row in rows]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, payload, revision FROM auto_roots WHERE id = ?",
                (item_id,),
            ).fetchone()
        return self._row(row) if row else None

    def get_item_by_public_id(self, public_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, payload, revision FROM auto_roots"
            ).fetchall()
        for row in rows:
            item = self._row(row)
            if item.get("public_id") == public_id:
                return item
        return None

    def save_item(
        self, item_id: str, definition: AutoDefinition, *, expected_revision: int | None
    ) -> dict[str, Any]:
        payload = definition.model_dump(mode="json")
        with self._database.transaction() as connection:
            existing = connection.execute(
                "SELECT revision FROM auto_roots WHERE id = ?", (item_id,)
            ).fetchone()
            current = int(existing["revision"]) if existing else None
            if expected_revision is not None and current != expected_revision:
                raise ValueError("auto_revision_conflict")
            rows = connection.execute(
                "SELECT id, payload FROM auto_roots WHERE id != ?", (item_id,)
            ).fetchall()
            if any(json.loads(row["payload"]).get("public_id") == definition.public_id for row in rows):
                raise ValueError("auto_public_id_conflict")
            revision = (current or 0) + 1
            connection.execute(
                "INSERT INTO auto_roots (id, payload, revision) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision",
                (item_id, json.dumps(payload, ensure_ascii=False), revision),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="auto-root",
            entity_id=item_id,
        )
        result = self.get_item(item_id)
        if result is None:
            raise RuntimeError("auto root was not readable after save")
        return result

    def delete_item(self, item_id: str) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM auto_roots WHERE id = ?", (item_id,))
            connection.commit()
        if cursor.rowcount != 1:
            return False
        emit_configuration_events(self._events, action="deleted", entity="auto-root", entity_id=item_id)
        return True
