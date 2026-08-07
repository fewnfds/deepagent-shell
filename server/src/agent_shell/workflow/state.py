from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Annotated, Any

from deepagents.middleware.filesystem import FilesystemState


def _mapping_update(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(left or {})
    result.update(right or {})
    return result


def _shared_update(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(left or {})
    result.update(deepcopy(right or {}))
    return result


class WorkflowState(FilesystemState, total=False):
    inputs: Annotated[dict[str, Any], _mapping_update]
    shared: Annotated[dict[str, Any], _shared_update]
    control: Annotated[dict[str, Any], _mapping_update]
    artifacts: Annotated[dict[str, Any], _mapping_update]
    ports: Annotated[dict[str, Any], _mapping_update]
    output: Annotated[dict[str, Any], _mapping_update]


def _parts(path: str) -> list[str]:
    values = [item for item in path.strip(".").split(".") if item]
    if not values or any(item in {"", ".", ".."} for item in values):
        raise ValueError("state path must contain at least one segment")
    return values


def read_path(value: Mapping[str, Any], path: str, default: Any = None) -> Any:
    current: Any = value
    for part in _parts(path):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def write_path(value: dict[str, Any], path: str, item: Any, operation: str = "set") -> dict[str, Any]:
    parts = _parts(path)
    result = deepcopy(value)
    current = result
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    key = parts[-1]
    if operation == "set":
        current[key] = deepcopy(item)
    elif operation == "append":
        existing = current.get(key)
        if existing is None:
            existing = []
            current[key] = existing
        if not isinstance(existing, list):
            raise ValueError(f"state path {path!r} is not a list")
        existing.append(deepcopy(item))
    elif operation == "merge":
        existing = current.get(key)
        if existing is None:
            existing = {}
            current[key] = existing
        if not isinstance(existing, dict) or not isinstance(item, dict):
            raise ValueError(f"state path {path!r} requires object values for merge")
        existing.update(deepcopy(item))
    else:
        raise ValueError(f"unsupported state update operation {operation!r}")
    return result
