from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.workflow.contracts import (
    WorkflowGraphDefinitionV1,
    WorkflowGraphDocumentV1,
    WorkflowLayoutV1,
)

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
            "filesystem_id": str(row["filesystem_id"]),
            "enabled": bool(row["enabled"]),
        }

    @staticmethod
    def _select(where: str = "") -> str:
        return (
            "SELECT id, name, description, filesystem_id, enabled "
            f"FROM workflows {where}"
        )

    def list_items(self, *, enabled_only: bool = False) -> list[dict]:
        where = "WHERE enabled = 1 " if enabled_only else ""
        with self._database.transaction() as connection:
            rows = connection.execute(
                self._select(where) + "ORDER BY name COLLATE NOCASE, id"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_item(self, item_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE id = ?"), (item_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_item_by_name(self, name: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE name = ?"), (name,)
            ).fetchone()
        return self._from_row(row) if row else None

    def get_item_by_filesystem(self, filesystem_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                self._select("WHERE filesystem_id = ?"), (filesystem_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def save_item(self, item_id: str, data: dict) -> None:
        empty_definition = WorkflowGraphDefinitionV1().model_dump_json()
        empty_layout = WorkflowLayoutV1().model_dump_json()
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
            connection.execute(
                "INSERT INTO workflows "
                "(id, name, description, filesystem_id, enabled, "
                "definition_json, layout_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "name = excluded.name, description = excluded.description, "
                "filesystem_id = excluded.filesystem_id, enabled = excluded.enabled",
                (
                    item_id,
                    data["name"],
                    data["description"],
                    data["filesystem_id"],
                    int(data["enabled"]),
                    empty_definition,
                    empty_layout,
                ),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity="workflow",
            entity_id=item_id,
        )

    def get_graph(self, item_id: str) -> WorkflowGraphDocumentV1 | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT definition_json, layout_json FROM workflows WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        return WorkflowGraphDocumentV1.model_validate(
            {
                "definition": json.loads(str(row["definition_json"])),
                "layout": json.loads(str(row["layout_json"])),
            }
        )

    def save_graph(
        self,
        item_id: str,
        document: WorkflowGraphDocumentV1,
    ) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE workflows SET definition_json = ?, layout_json = ? "
                "WHERE id = ?",
                (
                    document.definition.model_dump_json(),
                    document.layout.model_dump_json(),
                    item_id,
                ),
            )
            connection.commit()
        if cursor.rowcount != 1:
            return False
        emit_configuration_events(
            self._events,
            action="updated",
            entity="workflow",
            entity_id=item_id,
        )
        return True

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
