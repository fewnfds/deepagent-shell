from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from collections.abc import Callable
from typing import Any

from pydantic import SecretStr, ValidationError

from agent_shell.settings import Settings, SettingsError
from agent_shell.security import ApiKeyPolicyError, validate_api_key_policy
from agent_shell.storage.permissions import secure_file


_ACTIVE_SETTING = re.compile(r"^\s*(AGENT_SHELL_[A-Za-z0-9_]+)\s*=")


class SystemSettingsError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message_key: str,
        fallback: str,
        message_args: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        self.message_args = message_args or {}
        super().__init__(fallback)


def _secret_value(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


def _validation_keys(error: ValidationError) -> tuple[str, ...]:
    keys = {
        f"AGENT_SHELL_{str(item['loc'][0]).upper()}"
        for item in error.errors(include_input=False, include_url=False)
        if item.get("loc")
    }
    return tuple(sorted(keys))


def serialize_settings_file(settings: Settings, existing: str) -> str:
    preserved = [
        line
        for line in existing.splitlines()
        if _ACTIVE_SETTING.match(line) is None
    ]
    while preserved and not preserved[-1].strip():
        preserved.pop()
    values = [
        f"AGENT_SHELL_HOST={settings.host}",
        f"AGENT_SHELL_PORT={settings.port}",
        f"AGENT_SHELL_ALLOW_REMOTE={'true' if settings.allow_remote else 'false'}",
        "AGENT_SHELL_LANGSMITH_TRACING_ENABLED="
        f"{'true' if settings.langsmith_tracing_enabled else 'false'}",
        (
            "AGENT_SHELL_CORS_ORIGINS="
            + json.dumps(list(settings.cors_origins), separators=(",", ":"))
        ),
        (
            "AGENT_SHELL_TRUSTED_PROXY_CIDRS="
            + json.dumps(
                list(settings.trusted_proxy_cidrs), separators=(",", ":")
            )
        ),
        f"AGENT_SHELL_MANAGEMENT_TOKEN={_secret_value(settings.management_token)}",
    ]
    lines = [*preserved, *([""] if preserved else []), *values]
    return "\n".join(lines) + "\n"


def write_settings_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="agent-shell.env.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        permission = secure_file(temporary)
        if not permission.enforced:
            raise OSError("The settings file permissions are not private.")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class SystemSettingsService:
    def __init__(
        self,
        active: Settings,
        api_key_provider: Callable[[], str | None],
    ) -> None:
        self._active = active
        self._saved = active
        self._api_key_provider = api_key_provider

    @staticmethod
    def _public(settings: Settings) -> dict[str, Any]:
        return {
            "host": settings.host,
            "port": settings.port,
            "allow_remote": settings.allow_remote,
            "langsmith_tracing_enabled": settings.langsmith_tracing_enabled,
            "cors_origins": list(settings.cors_origins),
            "trusted_proxy_cidrs": list(settings.trusted_proxy_cidrs),
            "management_token": {
                "configured": settings.management_token is not None,
            },
        }

    @staticmethod
    def _same(left: Settings, right: Settings) -> bool:
        return (
            SystemSettingsService._public(left)
            == SystemSettingsService._public(right)
            and _secret_value(left.management_token)
            == _secret_value(right.management_token)
        )

    def get(self) -> dict[str, Any]:
        return {
            **self._public(self._saved),
            "restart_required": not self._same(self._active, self._saved),
        }

    @staticmethod
    def _apply_management_password(
        current: SecretStr | None,
        payload: dict[str, Any],
    ) -> str | None:
        operation = payload.get("operation")
        if operation == "preserve":
            return _secret_value(current)
        if operation == "replace":
            value = payload.get("value")
            if isinstance(value, str) and value:
                return value
        raise SystemSettingsError(
            422,
            "system_secret_operation_invalid",
            "errors.systemSecretOperationInvalid",
            "The secret update operation is invalid.",
        )

    def _candidate(self, payload: dict[str, Any]) -> Settings:
        values = {
            "host": payload["host"],
            "port": payload["port"],
            "allow_remote": payload["allow_remote"],
            "langsmith_tracing_enabled": payload["langsmith_tracing_enabled"],
            "management_token": self._apply_management_password(
                self._saved.management_token,
                payload["management_token"],
            ),
            "cors_origins": payload["cors_origins"],
            "trusted_proxy_cidrs": payload["trusted_proxy_cidrs"],
        }
        try:
            candidate = Settings(**values)
        except ValidationError as exc:
            keys = ", ".join(_validation_keys(exc))
            raise SystemSettingsError(
                422,
                "system_settings_invalid",
                "errors.systemSettingsInvalid",
                "The system settings are invalid.",
                {"keys": keys},
            ) from None
        candidate.bind_paths(self._active.application_home, self._active.data_root)
        try:
            candidate.validate_deployment()
        except SettingsError as exc:
            raise SystemSettingsError(
                422,
                "system_settings_invalid",
                "errors.systemSettingsInvalid",
                "The system settings are invalid.",
                {"keys": ", ".join(exc.keys)},
            ) from None
        try:
            validate_api_key_policy(candidate, self._api_key_provider())
        except ApiKeyPolicyError as exc:
            raise SystemSettingsError(
                422,
                exc.code,
                exc.message_key,
                exc.safe_message,
            ) from None
        return candidate

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = self._candidate(payload)
        path = self._active.environment_file
        if self._same(candidate, self._saved) and path.exists():
            self._saved = candidate
            return self.get()
        try:
            existing = path.read_text(encoding="utf-8-sig") if path.exists() else ""
            write_settings_file(path, serialize_settings_file(candidate, existing))
        except OSError as exc:
            raise SystemSettingsError(
                500,
                "system_settings_write_failed",
                "errors.systemSettingsWriteFailed",
                "The system settings could not be saved.",
            ) from exc
        self._saved = candidate
        return self.get()
