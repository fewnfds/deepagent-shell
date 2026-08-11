from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
import threading

from agent_shell.redaction import redact_for_boundary
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.storage.runtime_diagnostics import RuntimeDiagnosticStore


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
    ) -> None:
        self._lock = threading.Lock()
        self._store = store
        self._publish = publish
        self._logger = logging.getLogger(f"agent_shell.runtime.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        formatter = logging.Formatter("%(message)s")
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        self._logger.addHandler(console)

    def close(self) -> None:
        for handler in tuple(self._logger.handlers):
            handler.close()
            self._logger.removeHandler(handler)

    def snapshot(self) -> dict[str, object]:
        return self.settings() | {"entries": self._store.entries()}

    def settings(self) -> dict[str, int]:
        with self._lock:
            return self._store.retention()

    def set_retention_limit(self, retention_limit: int) -> dict[str, int]:
        self._store.set_retention(retention_limit)
        return self.settings()

    def delete_entries(
        self,
        predicate: Callable[[dict[str, object]], bool],
    ) -> int:
        return self._store.delete_entries(predicate)

    def runtime_error(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
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
    ) -> None:
        self._emit(
            "error",
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            code=code,
            exception_type=type(exc).__name__,
            message=message,
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
        self._publish({"type": "runtime_diagnostic", "entry": entry})
