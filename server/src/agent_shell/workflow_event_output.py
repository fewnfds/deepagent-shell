from __future__ import annotations

import ast
import builtins
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from pydantic_core import PydanticCustomError

from agent_shell.script_source import validate_module_function


OutputSource = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(max_length=100_000),
]
WorkflowEventName = Literal[
    "custom",
    "lifecycle",
    "values",
    "updates",
    "tasks",
    "checkpoints",
    "input",
    "input.requested",
    "debug",
    "other",
]
WORKFLOW_EVENT_NAMES = (
    "custom",
    "lifecycle",
    "values",
    "updates",
    "tasks",
    "checkpoints",
    "input",
    "input.requested",
    "debug",
    "other",
)
WORKFLOW_EVENT_FIELDS = {
    "custom": ("channel", "data_json"),
    "lifecycle": ("status", "finish_reason", "error_code"),
    "values": ("channel", "data_json"),
    "updates": ("channel", "data_json"),
    "tasks": ("channel", "data_json"),
    "checkpoints": ("channel", "data_json"),
    "input": ("channel", "data_json"),
    "input.requested": ("channel", "data_json"),
    "debug": ("channel", "data_json"),
    "other": ("channel", "data_json"),
}
DEFAULT_OUTPUT_SOURCE = "def output(event):\n    return event[\"message\"]\n"


def validate_output_source(source: str) -> str:
    validate_module_function(source, "output", asynchronous=False)
    tree = ast.parse(source, filename="output.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "output"
    )
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    if (
        [argument.arg for argument in positional] != ["event"]
        or arguments.vararg is not None
        or arguments.kwarg is not None
        or arguments.kwonlyargs
        or arguments.defaults
    ):
        raise ValueError("output must have exactly the signature output(event)")
    return source


class EventOutputScript(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    enabled: bool
    output_source: OutputSource

    @field_validator("output_source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return validate_output_source(value)


def validate_event_outputs(
    event_outputs: Mapping[str, EventOutputScript],
    expected_names: tuple[str, ...],
) -> None:
    expected = set(expected_names)
    actual = set(event_outputs)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise PydanticCustomError(
            "output_event_types_invalid",
            "Output event scripts do not match the current event types: {details}.",
            {"details": " ".join(details)},
        )


class WorkflowEventOutputBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    event_outputs: dict[WorkflowEventName, EventOutputScript]

    @model_validator(mode="after")
    def validate_outputs(self) -> "WorkflowEventOutputBlock":
        validate_event_outputs(self.event_outputs, WORKFLOW_EVENT_NAMES)
        return self


def compile_output(source: str) -> Callable[[dict[str, object]], str]:
    namespace: dict[str, Any] = {"__builtins__": builtins.__dict__}
    exec(compile(source, "<event-output>", "exec"), namespace, namespace)
    output = namespace["output"]

    def render(event: dict[str, object]) -> str:
        value = output(event=event)
        if not isinstance(value, str):
            raise TypeError("output(event) must return a string")
        return value

    return render


__all__ = [
    "DEFAULT_OUTPUT_SOURCE",
    "EventOutputScript",
    "WORKFLOW_EVENT_FIELDS",
    "WORKFLOW_EVENT_NAMES",
    "WorkflowEventOutputBlock",
    "WorkflowEventName",
    "compile_output",
    "validate_event_outputs",
    "validate_output_source",
]
