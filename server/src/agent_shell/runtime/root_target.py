from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


PUBLIC_ROOT_ID_PATTERN = re.compile(r"^[a-z]+(?:-[a-z]+)*$")


@dataclass(frozen=True, slots=True)
class RootTarget:
    kind: Literal["agent", "workflow"]
    id: str
    public_id: str
    name: str
    record: dict[str, Any]


def validate_public_root_id(public_id: str, *, kind: str) -> None:
    if not PUBLIC_ROOT_ID_PATTERN.fullmatch(public_id):
        raise ValueError("root public id must contain only lowercase words and hyphens")
    if not public_id.startswith(f"{kind}-"):
        raise ValueError("root public id prefix does not match its kind")


def agent_public_id(record: dict[str, Any]) -> str | None:
    value = record.get("public_id")
    if not isinstance(value, str):
        return None
    try:
        validate_public_root_id(value, kind="agent")
    except ValueError:
        return None
    return value


def workflow_public_id(record: dict[str, Any]) -> str | None:
    value = record.get("public_id")
    if not isinstance(value, str):
        return None
    try:
        validate_public_root_id(value, kind="workflow")
    except ValueError:
        return None
    return value
