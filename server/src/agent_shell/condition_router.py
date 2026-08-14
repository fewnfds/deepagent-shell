from __future__ import annotations

import ast
import builtins
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import fields
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agent_shell.python_requirements import parse_python_requirements
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import WorkflowState
from agent_shell.script_source import validate_module_function


BranchKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9-]*$"),
    Field(min_length=1, max_length=64),
]
ScriptSource = Annotated[str, StringConstraints(strip_whitespace=False)]
DEFAULT_CONDITION_ROUTER_SOURCE = (
    "async def route(state, context):\n"
    "    return {\"activate\": [\"otherwise\"], \"update\": {}}\n"
)


class ConditionRouterBranch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: BranchKey
    label: Annotated[str, Field(min_length=1, max_length=120)]


class ConditionRouterBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    branches: list[ConditionRouterBranch] = Field(
        default_factory=lambda: [
            ConditionRouterBranch(key="otherwise", label="Otherwise")
        ],
        min_length=1,
        max_length=100,
    )
    route_source: ScriptSource = Field(
        default=DEFAULT_CONDITION_ROUTER_SOURCE,
        max_length=100_000,
    )
    python_requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("python_requirements")
    @classmethod
    def validate_python_requirements(cls, values: list[str]) -> list[str]:
        return list(parse_python_requirements(values).values)

    @model_validator(mode="after")
    def validate_router(self) -> "ConditionRouterBlock":
        keys = [branch.key for branch in self.branches]
        if len(keys) != len(set(keys)):
            raise ValueError("condition router branch keys must be unique")
        if keys.count("otherwise") != 1:
            raise ValueError("condition router requires exactly one otherwise branch")
        validate_module_function(self.route_source, "route", asynchronous=True)
        tree = ast.parse(self.route_source, filename="route.py")
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "route"
        )
        arguments = function.args
        positional = [*arguments.posonlyargs, *arguments.args]
        if (
            [argument.arg for argument in positional] != ["state", "context"]
            or arguments.vararg is not None
            or arguments.kwarg is not None
            or arguments.kwonlyargs
            or arguments.defaults
        ):
            raise ValueError(
                "route must have exactly the async signature route(state, context)"
            )
        return self


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
    block: Mapping[str, Any],
    *,
    state: Mapping[str, Any],
    context: WorkflowRuntimeContext,
) -> ConditionRouterResult:
    configuration = ConditionRouterBlock.model_validate(block)
    namespace: dict[str, Any] = {"__builtins__": builtins.__dict__}
    original_state = _detached(state)
    script_state = _detached(state)
    try:
        exec(
            compile(configuration.route_source, "<condition-router>", "exec"),
            namespace,
            namespace,
        )
        value = await namespace["route"](
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
        declared = {branch.key for branch in configuration.branches}
        unknown = sorted(set(activate) - declared)
        if unknown:
            raise ValueError(
                "route activated undeclared branches: " + ", ".join(unknown)
            )
        if "otherwise" in activate and len(activate) != 1:
            raise ValueError("otherwise cannot be activated with another branch")
        return ConditionRouterResult(activate=activate, update=update)
    except Exception as exc:
        raise ConditionRouterError("condition router failed") from exc


__all__ = [
    "BranchKey",
    "ConditionRouterBlock",
    "ConditionRouterBranch",
    "ConditionRouterError",
    "ConditionRouterResult",
    "DEFAULT_CONDITION_ROUTER_SOURCE",
    "run_condition_router",
    "workflow_context_value",
]
