from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from itertools import chain
import logging
from pathlib import Path
import threading
import traceback

from agent_shell.redaction import redact_for_boundary
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.storage.runtime_debug_logs import RuntimeDebugLogStore
from agent_shell.storage.runtime_diagnostics import (
    RuntimeDiagnosticStore,
    runtime_diagnostic_id,
)


def _safe_text(value: object) -> str:
    safe = redact_for_boundary("request-trace", str(value or ""))
    return safe if isinstance(safe, str) else "[UNAVAILABLE]"


class RuntimeDiagnostics:
    """Persist bounded request-level diagnostics without Workflow internals."""

    def __init__(
        self,
        publish: Callable[[dict[str, object]], None],
        *,
        store: RuntimeDiagnosticStore,
        debug_logs: RuntimeDebugLogStore,
    ) -> None:
        self._lock = threading.Lock()
        self._store = store
        self._debug_logs = debug_logs
        self._publish = publish
        self._logger = logging.getLogger(f"agent_shell.runtime.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        formatter = logging.Formatter("%(message)s")
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        self._logger.addHandler(console)
        self._reconcile_debug_logs()

    def close(self) -> None:
        for handler in tuple(self._logger.handlers):
            handler.close()
            self._logger.removeHandler(handler)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._settings() | {"entries": self._store.entries()}

    def _settings(self) -> dict[str, object]:
        return self._store.retention() | self._debug_logs.settings()

    def settings(self) -> dict[str, object]:
        with self._lock:
            return self._settings()

    def set_retention_limit(self, retention_limit: int) -> dict[str, object]:
        with self._lock:
            self._store.set_retention(retention_limit)
            self._reconcile_debug_logs()
            return self._settings()

    def set_debug_enabled(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            self._debug_logs.set_enabled(enabled)
            return self._settings()

    def delete_entries(
        self,
        predicate: Callable[[dict[str, object]], bool],
    ) -> int:
        with self._lock:
            deleted = self._store.delete_entries(predicate)
            self._reconcile_debug_logs()
            return deleted

    def debug_log_path(self, item_id: str) -> Path | None:
        with self._lock:
            return self._debug_logs.download_path(item_id)

    def _reconcile_debug_logs(self) -> None:
        self._debug_logs.retain(
            {runtime_diagnostic_id(entry) for entry in self._store.entries()}
        )

    def runtime_error(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
        debug_exception: BaseException | None = None,
    ) -> None:
        message = (
            f"request failed code={_safe_text(code)} "
            f"message={_safe_text(exc.safe_message)}"
            if isinstance(exc, AgentRuntimeError)
            else f"request failed code={_safe_text(code)}"
        )
        self._emit_exception(
            exc,
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            code=code,
            message=message,
            debug_exception=exc if debug_exception is None else debug_exception,
        )

    def observation_error(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
    ) -> None:
        self._emit_exception(
            exc,
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            code=code,
            message=f"observation record failed code={_safe_text(code)}",
            debug_exception=exc,
        )

    def _emit_exception(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
        message: str,
        debug_exception: BaseException,
    ) -> None:
        self._emit(
            "error",
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            code=code,
            exception_type=type(exc).__name__,
            message=message,
            debug_exception=debug_exception,
        )

    def _emit(
        self,
        level: str,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        message: str,
        code: str = "",
        exception_type: str = "",
        debug_exception: BaseException | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        safe_model = _safe_text(model)
        safe_agent = _safe_text(agent_name)
        safe_request = _safe_text(request_id)
        safe_code = _safe_text(code)
        safe_exception_type = _safe_text(exception_type)
        prefix = (
            f"{now} [{level.upper()}] request_id={safe_request or '-'} "
            f"model={safe_model or '-'} agent={safe_agent or '-'}"
        )
        self._logger.log(
            {"debug": logging.DEBUG, "info": logging.INFO, "error": logging.ERROR}[level],
            prefix + "\n" + message,
        )
        with self._lock:
            try:
                entry = self._store.add(
                    timestamp=now,
                    level=level,
                    request_id=safe_request,
                    model=safe_model,
                    agent_name=safe_agent,
                    code=safe_code,
                    exception_type=safe_exception_type,
                    message=message,
                )
            except Exception:
                self._logger.error(prefix + "\nruntime diagnostic persistence failed")
                return
            if debug_exception is not None:
                try:
                    self._debug_logs.write(
                        runtime_diagnostic_id(entry),
                        chain(
                            (
                                f"timestamp={now}\n",
                                f"request_id={request_id}\n",
                                f"model={model}\n",
                                f"agent={agent_name}\n",
                                f"code={code}\n",
                                f"exception_type={type(debug_exception).__name__}\n\n",
                            ),
                            traceback.TracebackException.from_exception(
                                debug_exception,
                            ).format(chain=True),
                        ),
                    )
                except Exception:
                    self._logger.error(prefix + "\nruntime debug log persistence failed")
            try:
                self._reconcile_debug_logs()
            except Exception:
                self._logger.error(prefix + "\nruntime debug log cleanup failed")
        self._publish({"type": "runtime_diagnostic", "entry": entry})
