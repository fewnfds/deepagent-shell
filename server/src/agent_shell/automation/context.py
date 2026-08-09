from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol


_LOGGER = logging.getLogger("agent_shell.automation")


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class AutomationRequest:
    id: str
    messages: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    """Immutable Shell-owned data shared for one request lifecycle."""

    request_id: str
    messages: tuple[Mapping[str, Any], ...]
    assembly: Mapping[str, Any]
    input_sha: str
    agent_shas: Mapping[str, str]
    assembly_sha: str


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
        binding_kind: str,
        binding_index: int,
        plugin_id: str,
        plugin_dir: Path,
        runtime_dir: Path,
        mapped_paths: Mapping[str, Path],
        config: dict[str, Any],
        stage: str,
        initial_files: dict[str, str | bytes] | None = None,
        tick: int | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        self.request = request
        self.agent = MappingProxyType(
            {"id": owner_id, "type": owner_type, "name": owner_name}
        )
        self.plugin = MappingProxyType(
            {
                "id": plugin_id,
                "kind": binding_kind,
                "binding_index": binding_index,
            }
        )
        self.config = freeze(deepcopy(config))
        self.stage = stage
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
    messages: list[dict[str, Any]],
) -> AutomationRequest:
    frozen_messages = tuple(freeze(message) for message in deepcopy(messages))
    return AutomationRequest(id=request_id, messages=frozen_messages)
