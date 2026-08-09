from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


_LOGGER = logging.getLogger("agent_shell.middleware_packages")


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class MiddlewareRequest:
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
class MiddlewarePackagePaths:
    package_dir: Path
    runtime_dir: Path
    mapped: Mapping[str, Path]


class MiddlewarePackageContext:
    """Construction data for one request-local Middleware package binding."""

    def __init__(
        self,
        *,
        request: MiddlewareRequest,
        owner_id: str,
        owner_type: str,
        owner_name: str,
        binding_kind: str,
        binding_index: int,
        package_id: str,
        package_dir: Path,
        runtime_dir: Path,
        mapped_paths: Mapping[str, Path],
        config: dict[str, Any],
    ) -> None:
        self.request = request
        self.agent = MappingProxyType(
            {"id": owner_id, "type": owner_type, "name": owner_name}
        )
        self.package = MappingProxyType(
            {
                "id": package_id,
                "binding_index": binding_index,
            }
        )
        self.config = freeze(deepcopy(config))
        self.paths = MiddlewarePackagePaths(
            package_dir=package_dir,
            runtime_dir=runtime_dir,
            mapped=mapped_paths,
        )
    def log(self, message: object) -> None:
        _LOGGER.info(
            "middleware-package request=%s agent=%s package=%s: %s",
            self.request.id,
            self.agent["id"],
            self.package["id"],
            str(message)[:2000],
        )


def immutable_request(
    request_id: str,
    messages: list[dict[str, Any]],
) -> MiddlewareRequest:
    frozen_messages = tuple(freeze(message) for message in deepcopy(messages))
    return MiddlewareRequest(id=request_id, messages=frozen_messages)
