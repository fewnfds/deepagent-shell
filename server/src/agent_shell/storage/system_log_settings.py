from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_shell.storage.database import SQLiteDatabase


DEFAULT_SYSTEM_LOG_MAX_SIZE_MIB = 5
MIN_SYSTEM_LOG_MAX_SIZE_MIB = 1
MAX_SYSTEM_LOG_MAX_SIZE_MIB = 1024
MIB_BYTES = 1024 * 1024


class SystemLogSettingsStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def snapshot(self) -> dict[str, int]:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT max_size_mib FROM system_log_settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("system log settings are unavailable")
        return {
            "max_size_mib": int(row["max_size_mib"]),
            "min_size_mib": MIN_SYSTEM_LOG_MAX_SIZE_MIB,
            "max_size_mib_limit": MAX_SYSTEM_LOG_MAX_SIZE_MIB,
        }

    def set_max_size_mib(self, max_size_mib: int) -> dict[str, int]:
        if not MIN_SYSTEM_LOG_MAX_SIZE_MIB <= max_size_mib <= MAX_SYSTEM_LOG_MAX_SIZE_MIB:
            raise ValueError("system log maximum size is out of range")
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE system_log_settings SET max_size_mib = ? WHERE singleton = 1",
                (max_size_mib,),
            )
        return {
            "max_size_mib": max_size_mib,
            "min_size_mib": MIN_SYSTEM_LOG_MAX_SIZE_MIB,
            "max_size_mib_limit": MAX_SYSTEM_LOG_MAX_SIZE_MIB,
        }
