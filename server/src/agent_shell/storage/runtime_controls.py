from __future__ import annotations

from agent_shell.storage.file_config import FileConfigRepository


class RuntimeControlSettingsStore:
    """Persist runtime switches managed from the log center."""

    def __init__(self, repository: FileConfigRepository) -> None:
        self._repository = repository

    def snapshot(self) -> dict[str, bool]:
        values = self._repository.system().get("runtime_control", {})
        return {
            "debug_logging_enabled": bool(values.get("debug_logging_enabled", False)),
        }

    def set_debug_logging_enabled(self, enabled: bool) -> None:
        self._repository.update_system(lambda system: system.setdefault("runtime_control", {}).__setitem__("debug_logging_enabled", bool(enabled)))
