from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol


_LOGGER = logging.getLogger("agent_shell.automation")
_MAX_VARIABLE_BYTES = 256 * 1024


def _json_value(value: Any) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("automation variables must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > _MAX_VARIABLE_BYTES:
        raise ValueError("an automation variable may not exceed 256 KiB")
    return json.loads(encoded)


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)
    return value


class AutomationVariables:
    def __init__(
        self,
        request_values: dict[str, Any],
        agent_values: dict[str, Any],
        plugin_values: dict[str, Any],
    ) -> None:
        self._scopes = {
            "request": request_values,
            "agent": agent_values,
            "plugin": plugin_values,
        }

    @staticmethod
    def _split(path: str) -> tuple[str, str]:
        scope, separator, key = path.partition(".")
        if not separator or scope not in {"request", "agent", "plugin"} or not key:
            raise ValueError(
                "variable paths must use request.<key>, agent.<key>, or plugin.<key>"
            )
        return scope, key

    def get(self, path: str, default: Any = None) -> Any:
        scope, key = self._split(path)
        return deepcopy(self._scopes[scope].get(key, default))

    def set(self, path: str, value: Any) -> None:
        scope, key = self._split(path)
        self._scopes[scope][key] = _json_value(value)

    def delete(self, path: str) -> None:
        scope, key = self._split(path)
        self._scopes[scope].pop(key, None)


@dataclass(frozen=True, slots=True)
class AutomationRequest:
    id: str
    messages: tuple[Mapping[str, str], ...]


@dataclass(frozen=True, slots=True)
class AutomationPaths:
    plugin_dir: Path
    runtime_dir: Path
    mapped: Mapping[str, Path]


class AutomationRuntimeServices(Protocol):
    def prepare_skill(self, owner_id: str, name: str, *, mode: str) -> Path: ...


class AutomationContext:
    """Shell services for one request-local Agent/plugin binding."""

    def __init__(
        self,
        *,
        runtime: AutomationRuntimeServices,
        request: AutomationRequest,
        owner_id: str,
        owner_type: str,
        owner_name: str,
        binding_index: int,
        plugin_id: str,
        plugin_dir: Path,
        runtime_dir: Path,
        mapped_paths: Mapping[str, Path],
        config: dict[str, Any],
        variables: AutomationVariables,
        stage: str,
        messages: list[dict[str, str]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        tick: int | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        self.request = request
        self.agent = MappingProxyType(
            {"id": owner_id, "type": owner_type, "name": owner_name}
        )
        self.plugin = MappingProxyType(
            {"id": plugin_id, "binding_index": binding_index}
        )
        self.config = freeze(deepcopy(config))
        self.vars = variables
        self.stage = stage
        self.messages = messages
        self.initial_files = initial_files
        self.tick = tick
        self.terminal = freeze(dict(terminal)) if terminal is not None else None
        self.paths = AutomationPaths(
            plugin_dir=plugin_dir,
            runtime_dir=runtime_dir,
            mapped=mapped_paths,
        )
        self._runtime = runtime
        self._owner_id = owner_id

    def prepare_skill(self, name: str, mode: str = "overlay") -> Path:
        if self.stage != "prepare":
            raise ValueError("Skills may only be prepared during prepare")
        return self._runtime.prepare_skill(self._owner_id, name, mode=mode)

    def log(self, message: object) -> None:
        _LOGGER.info(
            "automation request=%s agent=%s plugin=%s: %s",
            self.request.id,
            self.agent["id"],
            self.plugin["id"],
            str(message)[:2000],
        )


def immutable_request(
    request_id: str,
    messages: list[dict[str, str]],
) -> AutomationRequest:
    frozen_messages = tuple(
        MappingProxyType(dict(message)) for message in deepcopy(messages)
    )
    return AutomationRequest(id=request_id, messages=frozen_messages)
