from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.database import SQLiteDatabase


class BlockStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        event_logger: SecurityEventLogger | None = None,
    ) -> None:
        self._database = database
        self._events = event_logger

    @staticmethod
    def _from_row(row: sqlite3.Row) -> dict:
        block = json.loads(row["payload"])
        block["id"] = row["id"]
        block["name"] = row["name"]
        return block

    @staticmethod
    def _public_model(block: dict, connection: sqlite3.Connection) -> dict:
        public = dict(block)
        credential = block.get("credential")
        if credential is None:
            public["credential"] = {"status": "missing"}
            return public
        if (
            not isinstance(credential, dict)
            or set(credential) != {"reference"}
            or not isinstance(credential.get("reference"), str)
            or not credential["reference"]
        ):
            # Repository validation reports the malformed storage metadata.
            # Public management reads remain repairable without exposing it.
            public["credential"] = {"status": "missing"}
            return public
        reference = credential["reference"]
        secret_exists = False
        if isinstance(reference, str) and reference:
            secret_exists = (
                connection.execute(
                    "SELECT 1 FROM provider_secrets WHERE id = ?", (reference,)
                ).fetchone()
                is not None
            )
        public["credential"] = {"status": "masked" if secret_exists else "missing"}
        return public

    def _public_from_row(
        self, row: sqlite3.Row, connection: sqlite3.Connection
    ) -> dict:
        block = self._from_row(row)
        if row["block_type"] == "model":
            return self._public_model(block, connection)
        return block

    def list_blocks(self, block_type: str) -> list[dict]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, block_type, name, payload FROM blocks WHERE block_type = ? "
                "ORDER BY name COLLATE NOCASE, id",
                (block_type,),
            ).fetchall()
            return [self._public_from_row(row, connection) for row in rows]

    def list_blocks_internal(self, block_type: str) -> list[dict]:
        """Return stored payloads for server-side validation without exposing secrets."""
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, block_type, name, payload FROM blocks WHERE block_type = ? "
                "ORDER BY name COLLATE NOCASE, id",
                (block_type,),
            ).fetchall()
            return [self._from_row(row) for row in rows]

    def list_block_headers(self) -> list[dict[str, str]]:
        """Return record identities so validation can detect unknown stored types."""
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT id, block_type, name FROM blocks "
                "ORDER BY block_type, name COLLATE NOCASE, id"
            ).fetchall()
            return [
                {
                    "id": str(row["id"]),
                    "block_type": str(row["block_type"]),
                    "name": str(row["name"]),
                }
                for row in rows
            ]

    def get_block_header(self, block_id: str) -> dict[str, str] | None:
        """Return one record identity without exposing its stored payload."""
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, block_type, name FROM blocks WHERE id = ?",
                (block_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "id": str(row["id"]),
                "block_type": str(row["block_type"]),
                "name": str(row["name"]),
            }

    def get_block(self, block_type: str, block_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, block_type, name, payload FROM blocks "
                "WHERE id = ? AND block_type = ?",
                (block_id, block_type),
            ).fetchone()
            return self._public_from_row(row, connection) if row else None

    def get_block_internal(self, block_type: str, block_id: str) -> dict | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT id, block_type, name, payload FROM blocks "
                "WHERE id = ? AND block_type = ?",
                (block_id, block_type),
            ).fetchone()
            return self._from_row(row) if row else None

    def save_block(self, block_type: str, block_id: str, data: dict) -> None:
        name = data["name"]
        credential_value: str | None = None
        secret_cleared = False
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT id FROM blocks WHERE block_type = ? AND name = ? AND id != ?",
                (block_type, name, block_id),
            ).fetchone()
            if duplicate:
                raise ValueError(f"名称「{name}」已存在")
            existing_row = connection.execute(
                "SELECT payload FROM blocks WHERE id = ? AND block_type = ?",
                (block_id, block_type),
            ).fetchone()
            existing = json.loads(existing_row["payload"]) if existing_row else {}
            stored = {key: value for key, value in data.items() if key != "name"}
            old_reference = (
                self._credential_reference(existing)
                if block_type == "model" and existing_row is not None
                else ""
            )
            if block_type == "model":
                credential_value = stored.pop("credential")
                reuse_existing_credential = (
                    existing_row is not None
                    and existing.get("base_url") == stored.get("base_url")
                    and existing.get("provider") == stored.get("provider")
                    and stored.get("provider") != "google_vertexai"
                )
                stored["credential"] = self._apply_credential_value(
                    connection,
                    existing.get("credential"),
                    credential_value,
                    reuse_existing=reuse_existing_credential,
                )
            payload = json.dumps(stored, ensure_ascii=False)
            connection.execute(
                "INSERT INTO blocks (id, block_type, name, payload) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, payload = excluded.payload",
                (block_id, block_type, name, payload),
            )
            new_reference = (
                self._credential_reference(stored) if block_type == "model" else ""
            )
            if old_reference and old_reference != new_reference:
                secret_cleared = self._delete_secret_if_unreferenced(
                    connection, old_reference
                )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="updated" if existing_row else "created",
            entity="block",
            entity_id=block_id,
            capability_type=block_type,
        )
        if self._events is not None:
            if credential_value is not None:
                self._events.emit(
                    "provider_secret_rotated",
                    {"block_id": block_id},
                )
            if secret_cleared:
                self._events.emit(
                    "provider_secret_cleared",
                    {
                        "block_id": block_id,
                        "reason": (
                            "replaced"
                            if credential_value is not None
                            else "connection_changed"
                        ),
                    },
                )

    @staticmethod
    def _credential_reference(payload: dict) -> str:
        credential = payload.get("credential")
        if credential is None:
            return ""
        if not isinstance(credential, dict):
            return ""
        reference = credential.get("reference")
        return reference if isinstance(reference, str) else ""

    @staticmethod
    def _apply_credential_value(
        connection: sqlite3.Connection,
        existing: object,
        credential: str | None,
        *,
        reuse_existing: bool,
    ) -> dict | None:
        if credential is None:
            if not reuse_existing:
                return None
            if existing is None:
                return None
            if isinstance(existing, dict) and set(existing) == {"reference"}:
                return dict(existing)
            raise ValueError("stored credential metadata is invalid")
        reference = str(uuid4())
        connection.execute(
            "INSERT INTO provider_secrets (id, secret_value) VALUES (?, ?)",
            (reference, credential),
        )
        return {"reference": reference}

    @staticmethod
    def _delete_secret_if_unreferenced(
        connection: sqlite3.Connection, reference: str
    ) -> bool:
        rows = connection.execute(
            "SELECT payload FROM blocks WHERE block_type = 'model'"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                continue
            if BlockStore._credential_reference(payload) == reference:
                return False
        connection.execute("DELETE FROM provider_secrets WHERE id = ?", (reference,))
        return True

    def copy_block(
        self,
        block_type: str,
        source_id: str,
        new_id: str,
        name: str,
    ) -> dict | None:
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT payload FROM blocks WHERE id = ? AND block_type = ?",
                (source_id, block_type),
            ).fetchone()
            if source is None:
                connection.rollback()
                return None
            duplicate = connection.execute(
                "SELECT 1 FROM blocks WHERE block_type = ? AND name = ?",
                (block_type, name),
            ).fetchone()
            if duplicate:
                raise ValueError(f"名称「{name}」已存在")
            connection.execute(
                "INSERT INTO blocks (id, block_type, name, payload) VALUES (?, ?, ?, ?)",
                (new_id, block_type, name, source["payload"]),
            )
            connection.commit()
        emit_configuration_events(
            self._events,
            action="copied",
            entity="block",
            entity_id=new_id,
            capability_type=block_type,
        )
        return self.get_block(block_type, new_id)

    @staticmethod
    def _detach_agent_block_references(
        connection: sqlite3.Connection,
        block_type: str,
        block_ids: set[str],
    ) -> None:
        for table in ("main_agents", "subagents"):
            rows = connection.execute(f"SELECT id, payload FROM {table}").fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                changed = False
                if table == "main_agents":
                    references = payload.get("capability_refs")
                    if isinstance(references, list):
                        retained = [
                            item
                            for item in references
                            if not (
                                isinstance(item, dict)
                                and item.get("type") == block_type
                                and item.get("block_id") in block_ids
                            )
                        ]
                        if len(retained) != len(references):
                            payload["capability_refs"] = retained
                            changed = True
                else:
                    settings = payload.get("settings")
                    overrides = (
                        settings.get("capability_overrides")
                        if isinstance(settings, dict)
                        else None
                    )
                    if isinstance(overrides, list):
                        retained = [
                            item
                            for item in overrides
                            if not (
                                isinstance(item, dict)
                                and item.get("type") == block_type
                                and item.get("block_id") in block_ids
                            )
                        ]
                        if len(retained) != len(overrides):
                            settings["capability_overrides"] = retained
                            changed = True
                if changed:
                    connection.execute(
                        f"UPDATE {table} SET payload = ? WHERE id = ?",
                        (json.dumps(payload, ensure_ascii=False), row["id"]),
                    )

    def delete_blocks(
        self,
        block_type: str,
        block_ids: list[str],
        *,
        detach_references: bool = False,
    ) -> int:
        unique_ids = list(dict.fromkeys(block_ids))
        if not unique_ids:
            return 0
        cleared_references: dict[str, str] = {}
        with self._database.transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ", ".join("?" for _ in unique_ids)
            rows = connection.execute(
                "SELECT id, payload FROM blocks "
                f"WHERE block_type = ? AND id IN ({placeholders})",
                [block_type, *unique_ids],
            ).fetchall()
            references = {
                str(row["id"]): self._credential_reference(json.loads(row["payload"]))
                for row in rows
                if block_type == "model"
            }
            if detach_references:
                self._detach_agent_block_references(
                    connection,
                    block_type,
                    {str(row["id"]) for row in rows},
                )
            connection.execute(
                "DELETE FROM blocks "
                f"WHERE block_type = ? AND id IN ({placeholders})",
                [block_type, *unique_ids],
            )
            for block_id, reference in references.items():
                if reference and self._delete_secret_if_unreferenced(
                    connection,
                    reference,
                ):
                    cleared_references[reference] = block_id
            connection.commit()
        existing_ids = {str(row["id"]) for row in rows}
        for block_id in unique_ids:
            if block_id not in existing_ids:
                continue
            emit_configuration_events(
                self._events,
                action="deleted",
                entity="block",
                entity_id=block_id,
                capability_type=block_type,
            )
        if self._events is not None:
            for block_id in cleared_references.values():
                self._events.emit(
                    "provider_secret_cleared",
                    {"block_id": block_id, "reason": "last_owner_deleted"},
                )
        return len(existing_ids)

    def delete_block(
        self,
        block_type: str,
        block_id: str,
        *,
        detach_references: bool = False,
    ) -> bool:
        return self.delete_blocks(
            block_type,
            [block_id],
            detach_references=detach_references,
        ) == 1
