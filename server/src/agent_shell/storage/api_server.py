from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from agent_shell.security_events import SecurityEventLogger, emit_configuration_events
from agent_shell.storage.history_retention import (
    HistoryRetentionStore,
    MAX_HISTORY_RETENTION_LIMIT,
)

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase
    from agent_shell.storage.file_config import FileConfigRepository


ApiKeyOperation = Literal["keep", "replace", "clear"]
class ApiServerStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        config_repository: FileConfigRepository,
        event_logger: SecurityEventLogger | None = None,
        history_retention: HistoryRetentionStore | None = None,
    ) -> None:
        self._database = database
        self._config_repository = config_repository
        self._events = event_logger
        self._history_retention = history_retention or HistoryRetentionStore(config_repository)
        with self._database.transaction() as connection:
            self._prune(
                connection,
                table="interception_test_records",
                order_column="intercepted_at",
                retention_limit=self._history_retention.get_limit_in(
                    connection, "interception_history"
                ),
            )
            connection.commit()

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
        if history_type != "interception_history":
            raise ValueError(f"unsupported history type: {history_type}")
        return {
            "retention_limit": self._history_retention.get_limit(history_type),
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def set_history_retention(
        self, history_type: str, retention_limit: int
    ) -> dict[str, int]:
        if history_type != "interception_history":
            raise ValueError(f"unsupported history type: {history_type}")
        targets = {
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
        return {
            "retention_limit": retention_limit,
            "max_retention_limit": MAX_HISTORY_RETENTION_LIMIT,
        }

    def settings(self) -> dict[str, object]:
        values = self._config_repository.system().get("api_server", {})
        return {
            "enabled": bool(values.get("enabled", True)),
            "api_key_configured": self.api_key() is not None,
            "max_initial_messages": int(values.get("max_initial_messages", 1000)),
        }

    def api_key(self) -> str | None:
        return self._config_repository.secret("AGENT_SHELL_API_KEY")

    def is_enabled(self) -> bool:
        return bool(self._config_repository.system().get("api_server", {}).get("enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        self._config_repository.update_system(lambda system: system.setdefault("api_server", {}).__setitem__("enabled", bool(enabled)))
        self._emit_updated(state="running" if enabled else "stopped")

    def update_settings(
        self,
        *,
        api_key_operation: ApiKeyOperation,
        api_key: str | None,
        max_initial_messages: int | None = None,
    ) -> None:
        if api_key_operation == "replace":
            self._config_repository.set_secret("AGENT_SHELL_API_KEY", api_key)
        elif api_key_operation == "clear":
            self._config_repository.set_secret("AGENT_SHELL_API_KEY", None)
        if max_initial_messages is not None:
            self._config_repository.update_system(
                lambda system: system.setdefault("api_server", {}).__setitem__("max_initial_messages", max_initial_messages)
            )
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

    def _emit_updated(self, *, state: str = "") -> None:
        emit_configuration_events(
            self._events,
            action="updated",
            entity="api-server",
            entity_id="singleton",
            state=state,
        )
