from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
from typing import Any

from agent_shell.provider_http import ProviderHttpClients
from agent_shell.provider_secrets import ProviderSecretResolver
from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.runtime.agent_runtime import AgentExecution, AgentRuntime
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.storage.schema import SCHEMA_SQL
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.validation.service import ConfigurationValidationService


class _SnapshotDatabase:
    """Private query-only image of one committed configuration view."""

    _TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("provider_secrets", ("id", "secret_value")),
        ("blocks", ("id", "block_type", "name", "payload")),
        ("main_agents", ("id", "name", "payload")),
        ("subagents", ("id", "component_name", "payload")),
    )

    def __init__(self, source: SQLiteDatabase) -> None:
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = sqlite3.connect(
            ":memory:", check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA_SQL)
        with source.transaction() as source_connection:
            source_connection.execute("BEGIN")
            for table, columns in self._TABLES:
                names = ", ".join(columns)
                rows = source_connection.execute(
                    f"SELECT {names} FROM {table}"
                ).fetchall()
                if rows:
                    placeholders = ", ".join("?" for _ in columns)
                    self._connection.executemany(
                        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                        [tuple(row[column] for column in columns) for row in rows],
                    )
        self._connection.commit()
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA query_only = ON")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            if connection is None:
                raise RuntimeError("request configuration snapshot is closed")
            yield connection

    def close(self) -> None:
        with self._lock:
            connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def __del__(self) -> None:  # pragma: no cover - interpreter timing varies
        try:
            self.close()
        except Exception:
            pass


@dataclass(slots=True)
class RequestRuntimeSnapshot:
    """Resolve a model and build exactly one request from one database image."""

    _configs: AgentConfigStore
    _runtime: AgentRuntime
    _database: _SnapshotDatabase

    def main_agent_by_name(self, name: str) -> dict[str, Any] | None:
        return self._configs.get_item_by_name("main_agents", name)

    async def start_agent(
        self,
        main_agent_id: str,
        raw_messages: object,
        **kwargs: Any,
    ) -> AgentExecution:
        try:
            return await self._runtime.start(main_agent_id, raw_messages, **kwargs)
        finally:
            # Agent construction has materialized every database-backed dependency.
            # Closing here makes any accidental lazy configuration read fail.
            self._database.close()


class RequestSnapshotRuntime:
    """Capture the latest committed configuration for each Agent construction."""

    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        custom_tools_dir: Path,
        automation_scripts_dir: Path,
        runtime_dir: Path,
        skills_dir: Path,
        diagnostics: RuntimeDiagnostics,
        provider_http_clients: ProviderHttpClients,
        media_outputs: MediaOutputStore,
    ) -> None:
        self._database = database
        self._custom_tools_dir = custom_tools_dir
        self._automation_scripts_dir = automation_scripts_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._diagnostics = diagnostics
        self._provider_http_clients = provider_http_clients
        self._media_outputs = media_outputs

    def capture(self) -> RequestRuntimeSnapshot:
        database = _SnapshotDatabase(self._database)
        try:
            blocks = BlockStore(database)  # type: ignore[arg-type]
            configs = AgentConfigStore(database)  # type: ignore[arg-type]
            secrets = ProviderSecretResolver(database)  # type: ignore[arg-type]
            automation_validation = AutomationValidationService(
                scripts_dir=self._automation_scripts_dir,
                runtime_root=self._runtime_dir,
            )
            validation = ConfigurationValidationService(
                blocks,
                configs,
                automation_validation,
                custom_tools_dir=self._custom_tools_dir,
            )
            runtime = AgentRuntime(
                AgentBuilder(
                    secrets,
                    custom_tools_dir=self._custom_tools_dir,
                    automation_scripts_dir=self._automation_scripts_dir,
                    runtime_dir=self._runtime_dir,
                    skills_dir=self._skills_dir,
                    validation=validation,
                    provider_http_clients=self._provider_http_clients,
                ),
                self._media_outputs,
                self._diagnostics,
            )
            return RequestRuntimeSnapshot(
                _configs=configs,
                _runtime=runtime,
                _database=database,
            )
        except Exception:
            database.close()
            raise
