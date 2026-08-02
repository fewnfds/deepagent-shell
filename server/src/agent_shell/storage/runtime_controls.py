from __future__ import annotations

from agent_shell.storage.database import SQLiteDatabase


class RuntimeControlSettingsStore:
    """Persist user-selected interception and diagnostic collection settings."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def snapshot(self) -> dict[str, bool]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT interception_enabled, verbose_diagnostics "
                "FROM runtime_control_settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("runtime control settings are unavailable")
        return {
            "interception_enabled": bool(row["interception_enabled"]),
            "verbose_diagnostics": bool(row["verbose_diagnostics"]),
        }

    def set_interception_enabled(self, enabled: bool) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE runtime_control_settings SET interception_enabled = ? "
                "WHERE singleton = 1",
                (int(enabled),),
            )

    def set_verbose_diagnostics(self, enabled: bool) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE runtime_control_settings SET verbose_diagnostics = ? "
                "WHERE singleton = 1",
                (int(enabled),),
            )
