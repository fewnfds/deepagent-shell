from __future__ import annotations

from collections.abc import Awaitable, Collection, Mapping, Sequence
from copy import deepcopy
from dataclasses import fields
from typing import TYPE_CHECKING, Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from agent_shell.python_packages.contracts import PythonPackageReference

if TYPE_CHECKING:
    from agent_shell.runtime.context import WorkflowRuntimeContext


BranchKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True),
    Field(min_length=1, max_length=64),
]
ConditionRouterCallable = Callable[[dict[str, Any], dict[str, Any]], Awaitable[Any]]


class ConditionRouterBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    python_package: PythonPackageReference


class ConditionRouterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activate: list[BranchKey] = Field(default_factory=list, max_length=100)
    update: dict[str, Any] = Field(default_factory=dict)

    @field_validator("activate")
    @classmethod
    def unique_branches(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("activated condition router branches must be unique")
        return values


class ConditionRouterError(RuntimeError):
    """Safe wrapper for user-authored routing failures."""


def _detached(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _detached(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_detached(item) for item in value]
    if isinstance(value, list):
        return [_detached(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_detached(item) for item in value]
    return deepcopy(value)


def workflow_context_value(context: WorkflowRuntimeContext) -> dict[str, Any]:
    """Project every current Runtime Context field into a detached mapping."""

    return {
        field.name: _detached(getattr(context, field.name))
        for field in fields(context)
    }


def _state_delta(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    from agent_shell.runtime.state import WorkflowState

    allowed = frozenset(WorkflowState.__annotations__)
    unexpected = sorted(set(after) - allowed)
    if unexpected:
        raise ValueError(
            "route modified unsupported Workflow State fields: "
            + ", ".join(unexpected)
        )
    deleted = sorted(set(before) - set(after))
    if deleted:
        raise ValueError(
            "route cannot delete Workflow State channels: " + ", ".join(deleted)
        )
    return {
        key: value
        for key, value in after.items()
        if key not in before or before[key] != value
    }


async def run_condition_router(
    route: ConditionRouterCallable,
    *,
    state: Mapping[str, Any],
    context: WorkflowRuntimeContext,
    allowed_branches: Collection[str],
) -> ConditionRouterResult:
    from agent_shell.runtime.state import WorkflowState

    original_state = _detached(state)
    script_state = _detached(state)
    try:
        value = await route(
            state=script_state,
            context=workflow_context_value(context),
        )
        result = ConditionRouterResult.model_validate(value)
        mutation_update = _state_delta(original_state, script_state)
        update = {**mutation_update, **result.update}
        unsupported_updates = sorted(
            set(update) - frozenset(WorkflowState.__annotations__)
        )
        if unsupported_updates:
            raise ValueError(
                "route returned unsupported Workflow State fields: "
                + ", ".join(unsupported_updates)
            )
        activate = result.activate or ["otherwise"]
        unknown = sorted(set(activate) - set(allowed_branches))
        if unknown:
            raise ValueError(
                "route activated branches without a matching Workflow edge: "
                + ", ".join(unknown)
            )
        if "otherwise" in activate and len(activate) != 1:
            raise ValueError("otherwise cannot be activated with another branch")
        return ConditionRouterResult(activate=activate, update=update)
    except Exception as exc:
        raise ConditionRouterError("condition router failed") from exc


__all__ = [
    "BranchKey",
    "ConditionRouterBlock",
    "ConditionRouterCallable",
    "ConditionRouterError",
    "ConditionRouterResult",
    "run_condition_router",
    "workflow_context_value",
]
