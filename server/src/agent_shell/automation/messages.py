from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_shell.runtime.input_messages import validate_prepared_messages


def thaw_message_value(value: Any) -> Any:
    """Copy immutable request containers without changing their leaf values."""
    if isinstance(value, Mapping):
        return {str(key): thaw_message_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_message_value(item) for item in value]
    return value


def mutable_request_messages(value: object) -> list[dict[str, Any]]:
    thawed = thaw_message_value(value)
    return validate_prepared_messages(thawed)


def prepared_transformed_messages(value: object) -> list[dict[str, Any]]:
    thawed = thaw_message_value(value)
    if not isinstance(thawed, Sequence) or isinstance(thawed, (str, bytes)):
        return validate_prepared_messages(thawed)

    after_non_system = False
    for item in thawed:
        if not isinstance(item, dict):
            after_non_system = True
            continue
        if item.get("role") == "system":
            if after_non_system:
                item["role"] = "user"
        else:
            after_non_system = True
    return validate_prepared_messages(thawed)


__all__ = [
    "mutable_request_messages",
    "prepared_transformed_messages",
    "thaw_message_value",
]
