from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


class AgentConfigStore:
    _IDENTITY_COLUMNS = {
        "main_agents": "name",
        "subagents": "component_name",
    }

    def __init__(
        self,
        database: SQLiteDatabase,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _from_row(row: sqlite3.Row, identity_column: str) -> dict:
        item = json.loads(row["payload"])
        item["id"] = row["id"]
        item[identity_column] = row[identity_column]
        return item

    def _table(self, table: str) -> str:
        if table not in self._IDENTITY_COLUMNS:
            raise ValueError(f"unsupported agent config table: {table}")
        return table

    def _identity_column(self, table: str) -> str:
        return self._IDENTITY_COLUMNS[self._table(table)]

    def list_items(self, table: str) -> list[dict]:
        table = self._table(table)
        identity_column = self._identity_column(table)
        with self._database.transaction() as connection:
            rows = connection.execute(
                f"SELECT id, {identity_column}, payload FROM {table} "
                f"ORDER BY {identity_column} COLLATE NOCASE, id"
            ).fetchall()
        return [self._from_row(row, identity_column) for row in rows]

    def get_item(self, table: str, item_id: str) -> dict | None:
        table = self._table(table)
        identity_column = self._identity_column(table)
        with self._database.transaction() as connection:
            row = connection.execute(
                f"SELECT id, {identity_column}, payload FROM {table} WHERE id = ?",
                (item_id,),
            ).fetchone()
        return self._from_row(row, identity_column) if row else None

    def get_item_by_name(self, table: str, name: str) -> dict | None:
        table = self._table(table)
        identity_column = self._identity_column(table)
        with self._database.transaction() as connection:
            row = connection.execute(
                f"SELECT id, {identity_column}, payload FROM {table} "
                f"WHERE {identity_column} = ?",
                (name,),
            ).fetchone()
        return self._from_row(row, identity_column) if row else None

    def save_item(self, table: str, item_id: str, data: dict) -> None:
        table = self._table(table)
        identity_column = self._identity_column(table)
        name = data[identity_column]
        payload = json.dumps(
            {key: value for key, value in data.items() if key != identity_column},
            ensure_ascii=False,
        )
        with self._database.transaction() as connection:
            existing = connection.execute(
                f"SELECT 1 FROM {table} WHERE id = ?", (item_id,)
            ).fetchone()
            duplicate = connection.execute(
                f"SELECT id FROM {table} WHERE {identity_column} = ? AND id != ?",
                (name, item_id),
            ).fetchone()
            if duplicate:
                raise ValueError(f"名称「{name}」已存在")
            connection.execute(
                f"INSERT INTO {table} (id, {identity_column}, payload) VALUES (?, ?, ?) "
                f"ON CONFLICT(id) DO UPDATE SET {identity_column} = excluded.{identity_column}, "
                "payload = excluded.payload",
                (item_id, name, payload),
            )
            connection.commit()
        entities = {
            "main_agents": "main-agent",
            "subagents": "subagent",
        }
        emit_configuration_events(
            self._events,
            action="updated" if existing else "created",
            entity=entities[table],
            entity_id=item_id,
        )

    @staticmethod
    def _detach_subagent_references(
        connection: sqlite3.Connection,
        target_ids: set[str],
    ) -> None:
        for table in ("main_agents", "subagents"):
            rows = connection.execute(f"SELECT id, payload FROM {table}").fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                if table == "main_agents":
                    references = payload.get("subagents")
                else:
                    settings = payload.get("settings")
                    references = (
                        settings.get("subagents")
                        if isinstance(settings, dict)
                        else None
                    )
                if not isinstance(references, list):
                    continue
                retained = [
                    reference
                    for reference in references
                    if not (
                        isinstance(reference, dict)
                        and reference.get("subagent_id") in target_ids
                    )
                ]
                if len(retained) == len(references):
                    continue
                if table == "main_agents":
                    payload["subagents"] = retained
                else:
                    settings["subagents"] = retained
                connection.execute(
                    f"UPDATE {table} SET payload = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), row["id"]),
                )

    def delete_items(
        self,
        table: str,
        item_ids: list[str],
        *,
        detach_references: bool = False,
    ) -> int:
        table = self._table(table)
        unique_ids = list(dict.fromkeys(item_ids))
        if not unique_ids:
            return 0
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ", ".join("?" for _ in unique_ids)
            existing = {
                str(row["id"])
                for row in connection.execute(
                    f"SELECT id FROM {table} WHERE id IN ({placeholders})",
                    unique_ids,
                ).fetchall()
            }
            if table == "subagents" and detach_references:
                self._detach_subagent_references(connection, existing)
            connection.execute(
                f"DELETE FROM {table} WHERE id IN ({placeholders})",
                unique_ids,
            )
            connection.commit()
        for item_id in unique_ids:
            if item_id not in existing:
                continue
            entities = {
                "main_agents": "main-agent",
                "subagents": "subagent",
            }
            emit_configuration_events(
                self._events,
                action="deleted",
                entity=entities[table],
                entity_id=item_id,
            )
        return len(existing)

    def delete_item(
        self,
        table: str,
        item_id: str,
        *,
        detach_references: bool = False,
    ) -> bool:
        return self.delete_items(
            table,
            [item_id],
            detach_references=detach_references,
        ) == 1
