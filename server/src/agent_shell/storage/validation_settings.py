from __future__ import annotations

from agent_shell.storage.database import SQLiteDatabase


MIN_VALIDATION_DEBOUNCE_MS = 100
MAX_VALIDATION_DEBOUNCE_MS = 10_000


class ConfigurationValidationSettingsStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def snapshot(self) -> dict[str, int]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT debounce_ms FROM configuration_validation_settings "
                "WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("configuration validation settings are unavailable")
        return self._response(int(row["debounce_ms"]))

    def update(self, debounce_ms: int) -> dict[str, int]:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE configuration_validation_settings SET debounce_ms = ? "
                "WHERE singleton = 1",
                (debounce_ms,),
            )
        return self._response(debounce_ms)

    @staticmethod
    def _response(debounce_ms: int) -> dict[str, int]:
        return {
            "debounce_ms": debounce_ms,
            "min_debounce_ms": MIN_VALIDATION_DEBOUNCE_MS,
            "max_debounce_ms": MAX_VALIDATION_DEBOUNCE_MS,
        }
