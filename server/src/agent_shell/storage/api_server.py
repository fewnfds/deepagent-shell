from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.history_retention import (
    HistoryRetentionStore,
    MAX_HISTORY_RETENTION_LIMIT,
)

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase
    from agent_shell.storage.media_outputs import MediaOutputStore


ApiKeyOperation = Literal["keep", "replace", "clear"]
MessageHistoryStatus = Literal[
    "completed",
    "failed",
    "client_disconnected",
]


class ApiServerStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        event_logger: SecurityEventLogger | None = None,
        history_retention: HistoryRetentionStore | None = None,
        media_outputs: MediaOutputStore | None = None,
    ) -> None:
        self._database = database
        self._events = event_logger
        self._history_retention = history_retention or HistoryRetentionStore(database)
        self._media_outputs = media_outputs
        with self._database.transaction() as connection:
            self._prune(
                connection,
                table="api_message_history",
                order_column="started_at",
                retention_limit=self._history_retention.get_limit_in(
                    connection, "api_history"
                ),
            )
            self._prune(
                connection,
                table="interception_test_records",
                order_column="intercepted_at",
                retention_limit=self._history_retention.get_limit_in(
                    connection, "interception_history"
                ),
            )
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()

    @staticmethod
    def _prune(
        connection,
        *,
        table: str,
        order_column: str,
        retention_limit: int,
    ) -> None:
        connection.execute(
            f"DELETE FROM {table} WHERE rowid NOT IN ("
            f"SELECT rowid FROM {table} "
            f"ORDER BY {order_column} DESC, rowid DESC LIMIT ?)",
            (retention_limit,),
        )

    def history_retention(self, history_type: str) -> dict[str, int]:
        return {
            "retention_limit": self._history_retention.get_limit(history_type),
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def set_history_retention(
        self, history_type: str, retention_limit: int
    ) -> dict[str, int]:
        targets = {
            "api_history": ("api_message_history", "started_at"),
            "interception_history": (
                "interception_test_records",
                "intercepted_at",
            ),
        }
        table, order_column = targets[history_type]
        with self._database.transaction() as connection:
            self._history_retention.set_limit_in(
                connection, history_type, retention_limit
            )
            self._prune(
                connection,
                table=table,
                order_column=order_column,
                retention_limit=retention_limit,
            )
            connection.commit()
        if self._media_outputs is not None and history_type == "api_history":
            self._media_outputs.cleanup_unreferenced()
        return {
            "retention_limit": retention_limit,
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def settings(self) -> dict[str, object]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT server.enabled, server.api_key, "
                "request.max_initial_messages "
                "FROM api_server_settings AS server "
                "CROSS JOIN api_server_request_settings AS request "
                "WHERE server.singleton = 1 AND request.singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("api server settings are unavailable")
        return {
            "enabled": bool(row["enabled"]),
            "api_key_configured": row["api_key"] is not None,
            "max_initial_messages": row["max_initial_messages"],
        }

    def api_key(self) -> str | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT api_key FROM api_server_settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("api server settings are unavailable")
        return row["api_key"]

    def is_enabled(self) -> bool:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT enabled FROM api_server_settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("api server settings are unavailable")
        return bool(row["enabled"])

    def set_enabled(self, enabled: bool) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE api_server_settings SET enabled = ? WHERE singleton = 1",
                (int(enabled),),
            )
            connection.commit()
        self._emit_updated(state="running" if enabled else "stopped")

    def update_settings(
        self,
        *,
        api_key_operation: ApiKeyOperation,
        api_key: str | None,
        max_initial_messages: int | None = None,
    ) -> None:
        with self._database.transaction() as connection:
            if api_key_operation == "replace":
                connection.execute(
                    "UPDATE api_server_settings SET api_key = ? WHERE singleton = 1",
                    (api_key,),
                )
            elif api_key_operation == "clear":
                connection.execute(
                    "UPDATE api_server_settings SET api_key = NULL WHERE singleton = 1"
                )
            if max_initial_messages is not None:
                connection.execute(
                    "UPDATE api_server_request_settings "
                    "SET max_initial_messages = ? WHERE singleton = 1",
                    (max_initial_messages,),
                )
            connection.commit()
        self._emit_updated()

    def add_interception_record(
        self,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        request_raw_json: str,
        model_request_raw_json: str,
    ) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        item = {
            "id": str(uuid4()),
            "name": now.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "intercepted_at": now.isoformat(timespec="milliseconds"),
            "request_id": request_id,
            "model": model,
            "agent_name": agent_name,
            "request_raw_json": request_raw_json,
            "model_request_raw_json": model_request_raw_json,
        }
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO interception_test_records "
                "(id, name, intercepted_at, request_id, model, agent_name, "
                "request_raw_json, model_request_raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["id"],
                    item["name"],
                    item["intercepted_at"],
                    item["request_id"],
                    item["model"],
                    item["agent_name"],
                    item["request_raw_json"],
                    item["model_request_raw_json"],
                ),
            )
            self._prune(
                connection,
                table="interception_test_records",
                order_column="intercepted_at",
                retention_limit=self._history_retention.get_limit_in(
                    connection, "interception_history"
                ),
            )
            connection.commit()
        return item

    def add_message_history(
        self,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        started_at: str,
        finished_at: str | None,
        status: MessageHistoryStatus,
        request_body: str,
        response_body: str | None,
        response_content_type: str | None,
        http_status: int | None,
        error_code: str | None,
        response_blocks: Sequence[dict[str, object]] = (),
        media_assets: Sequence[dict[str, object]] = (),
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "id": str(uuid4()),
            "request_id": request_id,
            "model": model,
            "agent_name": agent_name,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "request_body": request_body,
            "response_body": response_body,
            "response_content_type": response_content_type,
            "http_status": http_status,
            "error_code": error_code,
            "response_blocks_json": json.dumps(
                response_blocks, ensure_ascii=False, separators=(",", ":")
            ),
            "media_assets_json": json.dumps(
                media_assets, ensure_ascii=False, separators=(",", ":")
            ),
        }
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO api_message_history "
                "(id, request_id, model, agent_name, started_at, finished_at, "
                "status, request_body, response_body, response_content_type, "
                "http_status, error_code, response_blocks_json, media_assets_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(item[key] for key in (
                    "id",
                    "request_id",
                    "model",
                    "agent_name",
                    "started_at",
                    "finished_at",
                    "status",
                    "request_body",
                    "response_body",
                    "response_content_type",
                    "http_status",
                    "error_code",
                    "response_blocks_json",
                    "media_assets_json",
                )),
            )
            self._prune(
                connection,
                table="api_message_history",
                order_column="started_at",
                retention_limit=self._history_retention.get_limit_in(
                    connection, "api_history"
                ),
            )
            connection.commit()
        if self._media_outputs is not None:
            self._media_outputs.cleanup_unreferenced()
        return item

    def _emit_updated(self, *, state: str = "") -> None:
        emit_configuration_events(
            self._events,
            action="updated",
            entity="api-server",
            entity_id="singleton",
            state=state,
        )
