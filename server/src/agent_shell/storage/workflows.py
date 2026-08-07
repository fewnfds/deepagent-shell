from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.workflow.contracts import WorkflowDefinition, WorkflowRecord, workflow_payload

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
    def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"])
        payload["id"] = row["id"]
        payload["revision"] = row["revision"]
        payload["enabled"] = bool(row["enabled"])
        return payload

    def list_items(self) -> list[dict[str, Any]]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, public_id, payload, revision, enabled "
                "FROM workflows ORDER BY public_id COLLATE NOCASE, id"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, public_id, payload, revision, enabled FROM workflows WHERE id = ?",
                (item_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_item_by_public_id(self, public_id: str) -> dict[str, Any] | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, public_id, payload, revision, enabled "
                "FROM workflows WHERE public_id = ?",
                (public_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def save_item(
        self,
        item_id: str,
        definition: WorkflowDefinition,
        *,
        expected_revision: int | None,
    ) -> dict[str, Any]:
        payload = workflow_payload(definition)
        with self._database.transaction() as connection:
            existing = connection.execute(
                "SELECT revision FROM workflows WHERE id = ?", (item_id,)
            ).fetchone()
            current_revision = int(existing["revision"]) if existing else None
            if expected_revision is not None and current_revision != expected_revision:
                raise ValueError("workflow_revision_conflict")
            duplicate = connection.execute(
                "SELECT id FROM workflows WHERE public_id = ? AND id != ?",
                (definition.public_id, item_id),
            ).fetchone()
            if duplicate:
                raise ValueError("workflow_public_id_conflict")
            next_revision = (current_revision or 0) + 1
            connection.execute(
                "INSERT INTO workflows (id, public_id, payload, revision, enabled) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "public_id=excluded.public_id, payload=excluded.payload, "
                "revision=excluded.revision, enabled=excluded.enabled",
                (
                    item_id,
                    definition.public_id,
                    json.dumps(payload, ensure_ascii=False),
                    next_revision,
                    int(definition.enabled),
                ),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="workflow",
            entity_id=item_id,
        )
        result = self.get_item(item_id)
        if result is None:
            raise RuntimeError("workflow was not readable after save")
        return result

    def delete_item(self, item_id: str) -> bool:
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id FROM workflows WHERE id = ?", (item_id,)
            ).fetchone()
            if existing is None:
                connection.rollback()
                return False
            references = connection.execute(
                "SELECT id, payload FROM workflows WHERE id != ?",
                (item_id,),
            ).fetchall()
            if any(
                any(
                    isinstance(node, dict)
                    and node.get("type") == "builtin.workflow.call"
                    and isinstance(node.get("config"), dict)
                    and node["config"].get("workflow_id") == item_id
                    for node in json.loads(row["payload"]).get("nodes", [])
                )
                for row in references
            ):
                connection.rollback()
                raise ValueError("workflow_referenced")
            connection.execute("DELETE FROM workflows WHERE id = ?", (item_id,))
            connection.commit()
        emit_configuration_events(
            self._events,
            action="deleted",
            entity="workflow",
            entity_id=item_id,
        )
        return True
