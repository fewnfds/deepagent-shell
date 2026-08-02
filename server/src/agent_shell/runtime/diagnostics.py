from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import traceback

from agent_shell.provider_http import ProviderStreamError
from agent_shell.redaction import redact_for_boundary
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.output_stream import OutputEvent
from agent_shell.storage.runtime_controls import RuntimeControlSettingsStore
from agent_shell.storage.runtime_diagnostics import RuntimeDiagnosticStore


_VERBOSE_EVENT_TYPES = frozenset(
    {
        "lifecycle",
        "tool_call",
        "tool_result",
        "tool_error",
        "subagent",
    }
)


def _logical_path(filename: str) -> str:
    parts = Path(filename).parts
    for marker in ("agent_shell", "resources", "site-packages"):
        if marker in parts:
            index = parts.index(marker)
            selected = parts[index + 1 :] if marker == "site-packages" else parts[index:]
            return "/".join(selected)
    return "/".join(parts[-2:]) if len(parts) >= 2 else Path(filename).name


def _safe_text(value: object) -> str:
    safe = redact_for_boundary("request-trace", str(value or ""))
    return safe if isinstance(safe, str) else "[UNAVAILABLE]"


class RuntimeDiagnostics:
    """Sanitize runtime events, persist them once, and report them to stderr."""

    def __init__(
        self,
        publish: Callable[[dict[str, object]], None],
        *,
        store: RuntimeDiagnosticStore,
        control_settings: RuntimeControlSettingsStore,
    ) -> None:
        self._lock = threading.Lock()
        self._store = store
        self._control_settings = control_settings
        self._verbose = control_settings.snapshot()["verbose_diagnostics"]
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

    def settings(self) -> dict[str, object]:
        with self._lock:
            verbose = self._verbose
        return {"verbose": verbose} | self._store.retention()

    def set_verbose(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            self._control_settings.set_verbose_diagnostics(enabled)
            self._verbose = enabled
        return self.settings()

    def set_retention_limit(self, retention_limit: int) -> dict[str, object]:
        self._store.set_retention(retention_limit)
        return self.settings()

    def delete_entries(
        self,
        predicate: Callable[[dict[str, object]], bool],
    ) -> int:
        return self._store.delete_entries(predicate)

    def entries_for_request(self, request_id: str) -> list[dict[str, object]]:
        return self._store.entries(request_id=request_id) if request_id else []

    def request_started(self, *, request_id: str, model: str, agent_name: str) -> None:
        self._emit(
            "info",
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            message="request started",
        )

    def request_finished(
        self,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        status: str,
        duration_ms: int,
        finish_reason: str,
        reasoning_tokens: int | None,
    ) -> None:
        reasoning_value = (
            str(reasoning_tokens)
            if reasoning_tokens is not None
            else "unreported"
        )
        self._emit(
            "info",
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            message=(
                f"request {status} finish_reason={_safe_text(finish_reason)} "
                f"reasoning_tokens={reasoning_value} "
                f"duration_ms={duration_ms}"
            ),
        )

    def runtime_error(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
    ) -> None:
        headline = (
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
            headline=headline,
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
            headline=f"observation record failed code={_safe_text(code)}",
        )

    def _emit_exception(
        self,
        exc: BaseException,
        *,
        request_id: str,
        model: str,
        agent_name: str,
        code: str,
        headline: str,
    ) -> None:
        lines = [headline, "", "Sanitized traceback:"]
        chain: list[str] = []
        transport_details: list[str] = []
        current: BaseException | None = exc
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            chain.append(type(current).__name__)
            if isinstance(current, ProviderStreamError):
                transport_details.append(
                    f"  curl_code={current.curl_code} curl_error={current.curl_error}"
                )
            extracted = traceback.TracebackException(
                type(current), current, current.__traceback__, capture_locals=False
            )
            for frame in extracted.stack:
                lines.append(
                    f"  {_logical_path(frame.filename)}:{frame.lineno} in {frame.name}"
                )
            current = current.__cause__ or current.__context__
        if not chain:
            lines.append("  [UNAVAILABLE]")
        if transport_details:
            lines.extend(("", "Safe transport detail:", *transport_details))
        lines.extend(("", "Exception chain:", "  " + " -> ".join(chain)))
        self._emit(
            "error",
            request_id=request_id,
            model=model,
            agent_name=agent_name,
            code=code,
            exception_type=type(exc).__name__,
            message="\n".join(lines),
        )

    def runtime_event(self, event: OutputEvent, *, request_id: str, model: str) -> None:
        with self._lock:
            verbose = self._verbose
        if not verbose or event.event_type not in _VERBOSE_EVENT_TYPES:
            return
        values = event.template_values()
        fields = [event.event_type, event.phase]
        for label, key in (
            ("namespace", "namespace"),
            ("agent", "agent_name"),
            ("tool", "tool_name"),
            ("status", "status"),
        ):
            value = values.get(key, "")
            if value:
                fields.append(f"{label}={_safe_text(value)}")
        self._emit(
            "debug",
            request_id=request_id,
            model=model,
            agent_name=event.agent_name,
            message=" ".join(fields),
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
