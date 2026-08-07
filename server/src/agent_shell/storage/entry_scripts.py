from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.workflow.contracts import EntryScriptDefinition, entry_script_payload

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


class EntryScriptStore:
    def __init__(self, database: SQLiteDatabase, event_logger: SecurityEventLogger | None = None) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        result = json.loads(row["payload"])
        result.update(id=row["id"], revision=int(row["revision"]))
        return result

    def list_items(self) -> list[dict[str, Any]]:
        with self._database.transaction() as connection:
            rows = connection.execute("SELECT id, payload, revision FROM entry_scripts ORDER BY json_extract(payload, '$.name') COLLATE NOCASE, id").fetchall()
        return [self._row(row) for row in rows]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute("SELECT id, payload, revision FROM entry_scripts WHERE id = ?", (item_id,)).fetchone()
        return self._row(row) if row else None

    def get_item_by_name(self, name: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            rows = connection.execute("SELECT id, payload, revision FROM entry_scripts").fetchall()
        for row in rows:
            item = self._row(row)
            if item.get("name") == name:
                return item
        return None

    def save_item(self, item_id: str, definition: EntryScriptDefinition, *, expected_revision: int | None) -> dict[str, Any]:
        with self._database.transaction() as connection:
            existing = connection.execute("SELECT revision FROM entry_scripts WHERE id = ?", (item_id,)).fetchone()
            current = int(existing["revision"]) if existing else None
            if expected_revision is not None and current != expected_revision:
                raise ValueError("entry_script_revision_conflict")
            duplicates = connection.execute("SELECT id, payload FROM entry_scripts WHERE id != ?", (item_id,)).fetchall()
            if any(json.loads(row["payload"]).get("name") == definition.name for row in duplicates):
                raise ValueError("entry_script_name_conflict")
            revision = (current or 0) + 1
            connection.execute(
                "INSERT INTO entry_scripts (id, payload, revision) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision",
                (item_id, json.dumps(entry_script_payload(definition), ensure_ascii=False), revision),
            )
            connection.commit()
        emit_configuration_events(self._events, action="updated" if existing else "created", entity="entry-script", entity_id=item_id)
        result = self.get_item(item_id)
        if result is None:
            raise RuntimeError("entry script was not readable after save")
        return result

    def delete_item(self, item_id: str) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM entry_scripts WHERE id = ?", (item_id,))
            connection.commit()
        if cursor.rowcount != 1:
            return False
        emit_configuration_events(self._events, action="deleted", entity="entry-script", entity_id=item_id)
        return True
