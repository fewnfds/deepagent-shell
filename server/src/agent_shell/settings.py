from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import Field, PrivateAttr, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


ENV_PREFIX = "AGENT_SHELL_"
_LANGSMITH_TRACING_ENVIRONMENT = (
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_TRACING",
)


def bearer_token_is_valid(value: str) -> bool:
    return (
        bool(value)
        and value.isascii()
        and all(33 <= ord(character) <= 126 for character in value)
    )


class SettingsError(RuntimeError):
    """A startup-safe settings error that never includes setting values."""

    def __init__(self, keys: tuple[str, ...], action: str) -> None:
        self.keys = tuple(sorted(set(keys)))
        self.action = action
        joined = ", ".join(self.keys) if self.keys else f"{ENV_PREFIX}*"
        super().__init__(f"Invalid configuration for {joined}. {action}")


def _parse_string_list(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("must be a JSON array or comma-separated list")
            items = parsed
        else:
            items = stripped.split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise ValueError("must be a JSON array or comma-separated list")

    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("list entries must be non-empty strings")
        normalized.append(item.strip())
    if len(normalized) != len(set(normalized)):
        raise ValueError("list entries must be unique")
    return tuple(normalized)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    _application_home: Path = PrivateAttr(default_factory=lambda: Path.cwd().resolve())

    app_name: str = "agent-shell"
    host: str = "127.0.0.1"
    port: int = Field(default=19100, ge=1, le=65535)
    allow_remote: bool = False
    langsmith_tracing_enabled: bool = False
    management_token: SecretStr | None = None
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()
    trusted_proxy_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    _data_root: Path = PrivateAttr(default_factory=lambda: (Path.cwd() / "data").resolve())

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("must be an IPv4 or IPv6 literal") from exc
        if getattr(address, "scope_id", None):
            raise ValueError("scoped IPv6 addresses are not supported")
        return str(address)

    @field_validator("management_token")
    @classmethod
    def validate_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value()
        if not bearer_token_is_valid(secret):
            raise ValueError(
                "must be a non-empty printable ASCII value without spaces"
            )
        return value

    @field_validator("cors_origins", "trusted_proxy_cidrs", mode="before")
    @classmethod
    def parse_string_lists(cls, value: Any) -> tuple[str, ...]:
        return _parse_string_list(value)

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for origin in origins:
            if origin == "*":
                raise ValueError("wildcard origins are not supported")
            parsed = urlsplit(origin)
            try:
                port = parsed.port
            except ValueError as exc:
                raise ValueError("origin port is invalid") from exc
            if (
                parsed.scheme.lower() not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("must be an exact HTTP(S) origin without path or userinfo")
            scheme = parsed.scheme.lower()
            hostname = parsed.hostname.lower()
            if ":" in hostname:
                hostname = f"[{hostname}]"
            netloc = f"{hostname}:{port}" if port is not None else hostname
            normalized.append(f"{scheme}://{netloc}")
        if len(normalized) != len(set(normalized)):
            raise ValueError("normalized origins must be unique")
        return tuple(normalized)

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, cidrs: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for cidr in cidrs:
            try:
                network = ipaddress.ip_network(cidr, strict=True)
            except ValueError as exc:
                raise ValueError("must contain exact IPv4 or IPv6 CIDR networks") from exc
            normalized.append(str(network))
        if len(normalized) != len(set(normalized)):
            raise ValueError("normalized proxy networks must be unique")
        return tuple(normalized)

    @property
    def is_loopback(self) -> bool:
        return ipaddress.ip_address(self.host).is_loopback

    @property
    def deployment_mode(self) -> str:
        if self.allow_remote or not self.is_loopback or self.trusted_proxy_cidrs:
            return "authenticated_remote"
        return "authenticated_local"

    def validate_deployment(self) -> None:
        keys: set[str] = set()
        actions: list[str] = []
        if not self.is_loopback and not self.allow_remote:
            keys.update({"AGENT_SHELL_HOST", "AGENT_SHELL_ALLOW_REMOTE"})
            actions.append("Enable remote access explicitly or use a loopback host.")
        if self.trusted_proxy_cidrs and not self.allow_remote:
            keys.update(
                {"AGENT_SHELL_TRUSTED_PROXY_CIDRS", "AGENT_SHELL_ALLOW_REMOTE"}
            )
            actions.append("Trusted proxy deployment requires explicit remote access.")

        if self.management_token is None:
            keys.add("AGENT_SHELL_MANAGEMENT_TOKEN")
            actions.append("Configure the management Bearer token.")

        if actions:
            raise SettingsError(tuple(keys), " ".join(actions))

    @property
    def application_home(self) -> Path:
        return self._application_home

    @property
    def data_root(self) -> Path:
        return self._data_root

    @property
    def environment_file(self) -> Path:
        return self.data_root / "config" / "agent-shell.env"

    def bind_paths(self, application_home: Path, data_root: Path) -> None:
        self._application_home = application_home.resolve()
        self._data_root = data_root.resolve()

    def resolved_runtime_dir(self) -> Path:
        return self.application_home / "runtime"

    def resolved_logs_dir(self) -> Path:
        return self.data_root / "logs"

    def resolved_database_path(self) -> Path:
        return self.data_root / "state" / "agent-shell.sqlite3"

    def resolved_files_dir(self) -> Path:
        return self.data_root / "files"

    def resolved_media_outputs_dir(self) -> Path:
        return self.data_root / "media" / "outputs"

    def resolved_custom_tools_dir(self) -> Path:
        return self.data_root / "resources" / "custom_tools"

    def resolved_custom_middlewares_dir(self) -> Path:
        return self.data_root / "resources" / "custom_middlewares"

    def resolved_automation_scripts_dir(self) -> Path:
        return self.data_root / "resources" / "automation_scripts"

    def resolved_skills_dir(self) -> Path:
        return self.data_root / "resources" / "skills"

    def ensure_directories(self) -> None:
        directories = (
            self.data_root / "config",
            self.data_root / "state",
            self.resolved_files_dir(),
            self.resolved_media_outputs_dir(),
            self.resolved_custom_tools_dir(),
            self.resolved_custom_middlewares_dir(),
            self.resolved_automation_scripts_dir(),
            self.resolved_skills_dir(),
            self.resolved_logs_dir(),
            self.resolved_runtime_dir() / "cache",
            self.resolved_runtime_dir() / "tmp",
            self.resolved_runtime_dir() / "home",
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


def configure_project_langsmith_tracing(enabled: bool) -> None:
    """Apply the project-local LangSmith tracing boundary to this process.

    LangChain reads these variables directly from the process environment. Setting
    them here affects Agent Shell and its children only; it does not change the
    host user's or any other process's environment.
    """
    value = "true" if enabled else "false"
    for name in _LANGSMITH_TRACING_ENVIRONMENT:
        os.environ[name] = value


def _known_environment_keys() -> set[str]:
    return {f"{ENV_PREFIX}{name.upper()}" for name in Settings.model_fields}


def _unknown_environment_keys(environment: dict[str, str]) -> tuple[str, ...]:
    known = _known_environment_keys()
    return tuple(
        sorted(
            key
            for key in environment
            if key.upper().startswith(ENV_PREFIX) and key.upper() not in known
        )
    )


def _environment_file_keys(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    keys: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return ()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, _ = stripped.partition("=")
        name = name.strip()
        if separator and name:
            keys.append(name)
    return tuple(keys)


def _error_keys(exc: ValidationError) -> tuple[str, ...]:
    keys: set[str] = set()
    for error in exc.errors(include_input=False, include_url=False):
        location = error.get("loc") or ()
        if not location:
            continue
        field = str(location[0]).upper()
        keys.add(field if field.startswith(ENV_PREFIX) else f"{ENV_PREFIX}{field}")
    return tuple(keys)


class _PortableSettings(Settings):
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return init_settings, dotenv_settings


def load_settings(
    *,
    application_home: Path | None = None,
    data_root: Path | None = None,
    include_process_environment: bool = True,
) -> Settings:
    home = (application_home or Path.cwd()).resolve()
    root = data_root or (home / "data")
    root = root.resolve() if root.is_absolute() else (home / root).resolve()
    env_path = root / "config" / "agent-shell.env"
    process_unknown = (
        _unknown_environment_keys(dict(os.environ))
        if include_process_environment
        else ()
    )
    file_unknown = _unknown_environment_keys(
        {key: "" for key in _environment_file_keys(env_path)}
    )
    unknown = tuple(sorted(set(process_unknown) | set(file_unknown)))
    if unknown:
        raise SettingsError(unknown, "Remove or correct unknown AGENT_SHELL_* settings.")
    settings_type = Settings if include_process_environment else _PortableSettings
    try:
        settings = settings_type(_env_file=env_path)
    except ValidationError as exc:
        raise SettingsError(
            _error_keys(exc), "Correct the listed setting keys and restart."
        ) from None
    settings.bind_paths(home, root)
    return settings


def get_settings(
    *,
    application_home: Path | None = None,
    data_root: Path | None = None,
    include_process_environment: bool = True,
) -> Settings:
    settings = load_settings(
        application_home=application_home,
        data_root=data_root,
        include_process_environment=include_process_environment,
    )
    settings.validate_deployment()
    return settings
