from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.workflow.contracts import WorkflowDefinition, workflow_payload

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


class WorkflowStore:
    """Persistence for Graph Definitions only; run state lives in GraphRunStore."""

    def __init__(self, database: SQLiteDatabase, event_logger: SecurityEventLogger | None = None) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        payload["id"] = row["id"]
        payload["revision"] = int(row["revision"])
        payload["enabled"] = bool(row["enabled"])
        return payload

    def list_items(self) -> list[dict[str, Any]]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, payload, revision, enabled FROM workflows ORDER BY json_extract(payload, '$.name') COLLATE NOCASE, id"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, payload, revision, enabled FROM workflows WHERE id = ?", (item_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def save_item(self, item_id: str, definition: WorkflowDefinition, *, expected_revision: int | None) -> dict[str, Any]:
        payload = workflow_payload(definition)
        with self._database.transaction() as connection:
            existing = connection.execute("SELECT revision FROM workflows WHERE id = ?", (item_id,)).fetchone()
            current = int(existing["revision"]) if existing else None
            if expected_revision is not None and current != expected_revision:
                raise ValueError("workflow_revision_conflict")
            revision = (current or 0) + 1
            connection.execute(
                "INSERT INTO workflows (id, payload, revision, enabled) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision, enabled=excluded.enabled",
                (item_id, json.dumps(payload, ensure_ascii=False), revision, int(definition.enabled)),
            )
            connection.commit()
        emit_configuration_events(self._events, action="updated" if existing else "created", entity="workflow", entity_id=item_id)
        result = self.get_item(item_id)
        if result is None:
            raise RuntimeError("workflow was not readable after save")
        return result

    def delete_item(self, item_id: str) -> bool:
        with self._database.transaction() as connection:
            existing = connection.execute("SELECT id FROM workflows WHERE id = ?", (item_id,)).fetchone()
            if existing is None:
                return False
            references = connection.execute("SELECT payload FROM workflows WHERE id != ?", (item_id,)).fetchall()
            for row in references:
                payload = json.loads(row["payload"])
                if any(isinstance(n, dict) and n.get("type") == "builtin.workflow" and isinstance(n.get("config"), dict) and n["config"].get("graph_id") == item_id for n in payload.get("nodes", [])):
                    raise ValueError("workflow_referenced")
            connection.execute("DELETE FROM workflows WHERE id = ?", (item_id,))
            connection.commit()
        emit_configuration_events(self._events, action="deleted", entity="workflow", entity_id=item_id)
        return True
