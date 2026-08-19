from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable

import yaml


CONFIG_VERSION = 1
API_KEY_ENV = "AGENT_SHELL_API_KEY"
LANGSMITH_API_KEY_ENV = "LANGSMITH_API_KEY"


def _default_config() -> dict[str, Any]:
    return {
        "config_version": CONFIG_VERSION,
        "components": {},
        "main_agents": [],
        "subagents": [],
        "workflows": [],
    }


def _default_system() -> dict[str, Any]:
    return {
        "config_version": CONFIG_VERSION,
        "settings": {
            "host": "127.0.0.1",
            "port": 19100,
            "allow_remote": False,
            "langsmith_tracing_enabled": False,
            "langsmith_endpoint": "https://api.smith.langchain.com",
            "langsmith_project": "agent-shell",
            "langsmith_workspace_id": None,
            "cors_origins": [],
            "trusted_proxy_cidrs": [],
        },
        "api_server": {
            "enabled": True,
            "max_initial_messages": 1000,
            "message_interception_enabled": False,
        },
        "history_retention": {
            "runtime_diagnostics": 20,
        },
        "configuration_validation": {"debounce_ms": 1000},
        "system_log": {"max_size_mib": 5},
    }


def _read_yaml(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return deepcopy(default)
    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration file must contain a mapping: {path}")
    return value


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator and key.strip():
            values[key.strip()] = value.strip().strip('"')
    return values


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _dump_yaml(value: dict[str, Any]) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, default_flow_style=False)


class FileConfigRepository:
    """Persistent configuration repository backed by layered YAML files."""

    _COMPONENT_DIR = "components"

    def __init__(
        self,
        data_root: Path,
        *,
        _config: dict[str, Any] | None = None,
        _system: dict[str, Any] | None = None,
        _env: dict[str, str] | None = None,
        _persist: bool = True,
    ) -> None:
        self.data_root = data_root.resolve()
        self.config_root = self.data_root / "config"
        self.components_root = self.config_root / self._COMPONENT_DIR
        self.agents_root = self.config_root / "agents"
        self.workflows_root = self.config_root / "workflows"
        self.system_path = self.config_root / "system.yaml"
        self.environment_path = self.config_root / "agent-shell.env"
        self._lock = threading.RLock()
        self._persist = _persist
        self._config = deepcopy(_config) if _config is not None else self._load_config()
        self._system = deepcopy(_system) if _system is not None else _read_yaml(self.system_path, _default_system())
        loaded_environment = dict(_env) if _env is not None else _read_env(self.environment_path)
        allowed_environment = self._allowed_environment_names(self._config)
        self._env = {
            name: value
            for name, value in loaded_environment.items()
            if name in allowed_environment
        }
        self._normalize()
        if self._persist and not self.system_path.exists():
            _write_atomic(self.system_path, _dump_yaml(self._system))

    def _load_config(self) -> dict[str, Any]:
        config = _default_config()
        for directory in self.components_root.glob("*") if self.components_root.exists() else ():
            if not directory.is_dir():
                continue
            records: list[dict[str, Any]] = []
            for path in sorted(directory.glob("*.yaml")):
                document = _read_yaml(path, {})
                payload = document.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError(f"component payload must be a mapping: {path}")
                record = {**deepcopy(payload), "id": document.get("id"), "name": document.get("name")}
                if directory.name == "model" and isinstance(record.get("credential"), str) and record["credential"].startswith("$"):
                    record["credential"] = {"reference": record["credential"][1:]}
                records.append(record)
            config["components"][directory.name] = records

        for category, key, identity in (("main", "main_agents", "name"), ("subagent", "subagents", "component_name")):
            directory = self.agents_root / category
            records: list[dict[str, Any]] = []
            if directory.exists():
                for path in sorted(directory.glob("*.yaml")):
                    document = _read_yaml(path, {})
                    payload = document.get("payload")
                    if not isinstance(payload, dict):
                        raise ValueError(f"agent payload must be a mapping: {path}")
                    records.append({**deepcopy(payload), "id": document.get("id"), identity: document.get(identity)})
            config[key] = records

        if self.workflows_root.exists():
            for path in sorted(self.workflows_root.glob("*.yaml")):
                document = _read_yaml(path, {})
                payload = document.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError(f"workflow payload must be a mapping: {path}")
                config["workflows"].append({**deepcopy(payload), "id": document.get("id")})
        return config

    @staticmethod
    def _normalize_config(config: dict[str, Any]) -> None:
        config.setdefault("config_version", CONFIG_VERSION)
        config.setdefault("components", {})
        config.setdefault("main_agents", [])
        config.setdefault("subagents", [])
        config.setdefault("workflows", [])
        components = config["components"]
        if not isinstance(components, dict):
            raise ValueError("config components must be a mapping")

    @staticmethod
    def _normalize_system(system: dict[str, Any]) -> None:
        system.setdefault("config_version", CONFIG_VERSION)
        defaults = _default_system()
        for section, value in defaults.items():
            if section == "config_version":
                continue
            current = system.setdefault(section, {})
            if isinstance(current, dict) and isinstance(value, dict):
                for key, default in value.items():
                    current.setdefault(key, deepcopy(default))
        system.pop("runtime_control", None)
        system.pop("runtime_diagnostics", None)
        history_retention = system.get("history_retention")
        if isinstance(history_retention, dict):
            history_retention.pop("runtime_log", None)
            history_retention.pop("workflow_debug_history", None)

    def _normalize(self) -> None:
        self._normalize_config(self._config)
        self._normalize_system(self._system)

    @staticmethod
    def _allowed_environment_names(config: dict[str, Any]) -> set[str]:
        names = {
            "AGENT_SHELL_MANAGEMENT_TOKEN",
            API_KEY_ENV,
            LANGSMITH_API_KEY_ENV,
        }
        models = config.get("components", {}).get("model", [])
        if not isinstance(models, list):
            return names
        for model in models:
            credential = model.get("credential") if isinstance(model, dict) else None
            reference = credential.get("reference") if isinstance(credential, dict) else None
            if isinstance(reference, str) and reference:
                names.add(reference)
        return names

    @classmethod
    def empty(cls, data_root: Path) -> "FileConfigRepository":
        return cls(data_root, _config=_default_config(), _system=_default_system(), _env=_read_env(data_root / "config" / "agent-shell.env"), _persist=False)

    def clone(self) -> "FileConfigRepository":
        with self._lock:
            return FileConfigRepository(self.data_root, _config=self._config, _system=self._system, _env=self._env, _persist=False)

    def config(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._config)

    def system(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._system)

    def update_config(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        with self._lock:
            candidate = deepcopy(self._config)
            result = mutator(candidate)
            self._normalize_config(candidate)
            try:
                self._flush_config(candidate)
            except BaseException:
                try:
                    self._flush_config(self._config)
                except BaseException:
                    pass
                raise
            self._config = candidate
            return result

    def update_system(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        with self._lock:
            candidate = deepcopy(self._system)
            result = mutator(candidate)
            self._normalize_system(candidate)
            if self._persist:
                _write_atomic(self.system_path, _dump_yaml(candidate))
            self._system = candidate
            return result

    def update_config_and_environment(
        self,
        mutator: Callable[[dict[str, Any], dict[str, str]], Any],
    ) -> Any:
        with self._lock:
            original_config = deepcopy(self._config)
            original_environment = dict(self._env)
            candidate_config = deepcopy(self._config)
            candidate_environment = dict(self._env)
            result = mutator(candidate_config, candidate_environment)
            self._normalize_config(candidate_config)
            self._commit_config_and_environment(
                original_config,
                original_environment,
                candidate_config,
                candidate_environment,
            )
            self._config = candidate_config
            self._env = candidate_environment
            return result

    def update_system_and_environment(
        self,
        mutator: Callable[[dict[str, Any], dict[str, str]], Any],
    ) -> Any:
        with self._lock:
            original_system = deepcopy(self._system)
            original_environment = dict(self._env)
            candidate_system = deepcopy(self._system)
            candidate_environment = dict(self._env)
            result = mutator(candidate_system, candidate_environment)
            self._normalize_system(candidate_system)
            staged_environment = {**original_environment, **candidate_environment}
            try:
                if staged_environment != original_environment:
                    self._write_environment(staged_environment)
                if self._persist:
                    _write_atomic(self.system_path, _dump_yaml(candidate_system))
                if candidate_environment != staged_environment:
                    self._write_environment(candidate_environment)
            except BaseException:
                try:
                    if self._persist:
                        _write_atomic(self.system_path, _dump_yaml(original_system))
                    self._write_environment(original_environment)
                except BaseException:
                    pass
                raise
            self._system = candidate_system
            self._env = candidate_environment
            return result

    def secret(self, name: str) -> str | None:
        with self._lock:
            return self._env.get(name)

    def set_secret(self, name: str, value: str | None) -> None:
        with self._lock:
            candidate = dict(self._env)
            if value is None:
                candidate.pop(name, None)
            else:
                candidate[name] = value
            self._write_environment(candidate)
            self._env = candidate

    def _write_environment(self, environment: dict[str, str]) -> None:
        if not self._persist:
            return
        lines = [f"{key}={item}" for key, item in sorted(environment.items())]
        _write_atomic(
            self.environment_path,
            "\n".join(lines) + ("\n" if lines else ""),
        )

    def _commit_config_and_environment(
        self,
        original_config: dict[str, Any],
        original_environment: dict[str, str],
        candidate_config: dict[str, Any],
        candidate_environment: dict[str, str],
    ) -> None:
        staged_environment = {**original_environment, **candidate_environment}
        try:
            if staged_environment != original_environment:
                self._write_environment(staged_environment)
            self._flush_config(candidate_config)
            if candidate_environment != staged_environment:
                self._write_environment(candidate_environment)
        except BaseException:
            try:
                self._flush_config(original_config)
                self._write_environment(original_environment)
            except BaseException:
                pass
            raise

    def _flush_config(self, config: dict[str, Any]) -> None:
        if not self._persist:
            return
        self.components_root.mkdir(parents=True, exist_ok=True)
        expected: set[Path] = set()
        for block_type, records in config.get("components", {}).items():
            directory = self.components_root / str(block_type)
            directory.mkdir(parents=True, exist_ok=True)
            for record in records:
                if not isinstance(record, dict) or not record.get("id"):
                    continue
                document = {"kind": "component", "type": block_type, "schema_version": CONFIG_VERSION, "id": record["id"], "name": record.get("name", ""), "payload": self._serialize_record(record, block_type)}
                path = directory / f"{record['id']}.yaml"
                expected.add(path)
                _write_atomic(path, _dump_yaml(document))
        self._write_agents(config, expected)
        self._write_workflows(config, expected)
        for directory in (
            self.components_root,
            self.agents_root,
            self.workflows_root,
        ):
            if not directory.exists():
                continue
            for path in directory.rglob("*.yaml"):
                if path not in expected:
                    path.unlink(missing_ok=True)

    def _write_agents(self, config: dict[str, Any], expected: set[Path]) -> None:
        for category, key, identity, kind in (("main", "main_agents", "name", "main_agent"), ("subagent", "subagents", "component_name", "subagent")):
            directory = self.agents_root / category
            directory.mkdir(parents=True, exist_ok=True)
            for record in config.get(key, []):
                if not isinstance(record, dict) or not record.get("id"):
                    continue
                path = directory / f"{record['id']}.yaml"
                expected.add(path)
                payload = {k: deepcopy(v) for k, v in record.items() if k not in {"id", identity}}
                _write_atomic(path, _dump_yaml({"kind": kind, "schema_version": CONFIG_VERSION, "id": record["id"], identity: record.get(identity, ""), "payload": payload}))

    def _write_workflows(
        self, config: dict[str, Any], expected: set[Path]
    ) -> None:
        self.workflows_root.mkdir(parents=True, exist_ok=True)
        for record in config.get("workflows", []):
            if not isinstance(record, dict) or not record.get("id"):
                continue
            path = self.workflows_root / f"{record['id']}.yaml"
            expected.add(path)
            payload = {k: deepcopy(v) for k, v in record.items() if k != "id"}
            _write_atomic(path, _dump_yaml({"kind": "workflow", "schema_version": CONFIG_VERSION, "id": record["id"], "payload": payload}))

    @staticmethod
    def _serialize_record(record: dict, block_type: str) -> dict:
        payload = {k: deepcopy(v) for k, v in record.items() if k not in {"id", "name"}}
        if block_type == "model":
            credential = payload.get("credential")
            if isinstance(credential, dict) and isinstance(credential.get("reference"), str):
                payload["credential"] = f"${credential['reference']}"
        return payload
