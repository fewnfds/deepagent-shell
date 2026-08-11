from __future__ import annotations

from agent_shell.storage.file_config import FileConfigRepository


class RuntimeControlSettingsStore:
    """Persist user-selected interception and diagnostics settings in system.yaml."""

    def __init__(self, repository: FileConfigRepository) -> None:
        self._repository = repository

    def snapshot(self) -> dict[str, bool]:
        values = self._repository.system().get("runtime_control", {})
        return {
            "interception_enabled": bool(values.get("interception_enabled", False)),
            "verbose_diagnostics": bool(values.get("verbose_diagnostics", False)),
        }

    def set_interception_enabled(self, enabled: bool) -> None:
        self._repository.update_system(lambda system: system.setdefault("runtime_control", {}).__setitem__("interception_enabled", bool(enabled)))

    def set_verbose_diagnostics(self, enabled: bool) -> None:
        self._repository.update_system(lambda system: system.setdefault("runtime_control", {}).__setitem__("verbose_diagnostics", bool(enabled)))
