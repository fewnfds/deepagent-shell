from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import re
import tempfile
import threading

from agent_shell.storage.permissions import secure_directory, secure_file
from agent_shell.storage.runtime_controls import RuntimeControlSettingsStore


_RUNTIME_DIAGNOSTIC_ID = re.compile(r"^[0-9a-f]{64}$")


class RuntimeDebugLogStore:
    """Persist unrestricted exception logs outside the summary database."""

    def __init__(
        self,
        directory: Path,
        controls: RuntimeControlSettingsStore,
    ) -> None:
        self._lock = threading.Lock()
        self._directory = directory
        self._controls = controls
        self.directory_permission = secure_directory(directory)

    def settings(self) -> dict[str, bool]:
        return {
            "debug_enabled": self._controls.snapshot()["debug_logging_enabled"],
        }

    def set_enabled(self, enabled: bool) -> dict[str, bool]:
        self._controls.set_debug_logging_enabled(enabled)
        return {"debug_enabled": bool(enabled)}

    @staticmethod
    def _validate_id(item_id: str) -> str:
        if not _RUNTIME_DIAGNOSTIC_ID.fullmatch(item_id):
            raise ValueError("runtime diagnostic id is invalid")
        return item_id

    def _path(self, item_id: str) -> Path:
        return self._directory / f"runtime-{self._validate_id(item_id)}.log"

    def write(self, item_id: str, lines: Iterable[str]) -> None:
        if not self.settings()["debug_enabled"]:
            return
        path = self._path(item_id)
        temporary: Path | None = None
        with self._lock:
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    newline="",
                    dir=self._directory,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as stream:
                    temporary = Path(stream.name)
                    for line in lines:
                        stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
                secure_file(temporary)
                os.replace(temporary, path)
            except Exception:
                raise
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def download_path(self, item_id: str) -> Path | None:
        path = self._path(item_id)
        with self._lock:
            return path if path.is_file() else None

    def retain(self, item_ids: set[str]) -> None:
        expected = {self._path(item_id) for item_id in item_ids}
        with self._lock:
            for path in self._directory.glob("runtime-*.log"):
                if path not in expected:
                    path.unlink(missing_ok=True)


__all__ = ["RuntimeDebugLogStore"]
