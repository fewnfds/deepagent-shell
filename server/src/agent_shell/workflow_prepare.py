from __future__ import annotations

import builtins
from copy import deepcopy
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from agent_shell.python_requirements import parse_python_requirements
from agent_shell.script_source import validate_module_function


ScriptSource = Annotated[str, StringConstraints(strip_whitespace=False)]
DEFAULT_WORKFLOW_PREPARE_SOURCE = (
    "async def prepare(input):\n"
    "    return {\"context\": {}}\n"
)


class WorkflowPrepareBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    enabled: bool = True
    prepare_source: ScriptSource = Field(
        default=DEFAULT_WORKFLOW_PREPARE_SOURCE,
        max_length=100_000,
    )
    python_requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("python_requirements")
    @classmethod
    def validate_python_requirements(cls, values: list[str]) -> list[str]:
        return list(parse_python_requirements(values).values)

    @model_validator(mode="after")
    def validate_source(self) -> "WorkflowPrepareBlock":
        validate_module_function(self.prepare_source, "prepare", asynchronous=True)
        return self


class WorkflowPrepareResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowPrepareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: dict[str, JsonValue]
    workflow: dict[str, JsonValue]
    agents: dict[str, JsonValue]


class WorkflowPrepareError(RuntimeError):
    """Safe pre-LangChain preparation failure."""


async def run_workflow_prepare(
    block: dict[str, Any],
    *,
    input_value: dict[str, Any],
) -> WorkflowPrepareResult:
    configuration = WorkflowPrepareBlock.model_validate(block)
    if not configuration.enabled:
        return WorkflowPrepareResult()
    namespace: dict[str, Any] = {"__builtins__": builtins.__dict__}
    try:
        exec(
            compile(configuration.prepare_source, "<workflow-prepare>", "exec"),
            namespace,
            namespace,
        )
        prepare = namespace["prepare"]
        prepared_input = WorkflowPrepareInput.model_validate(input_value).model_dump(
            mode="json"
        )
        value = await prepare(input=deepcopy(prepared_input))
        return WorkflowPrepareResult.model_validate(value)
    except Exception as exc:
        raise WorkflowPrepareError("workflow prepare failed") from exc


WORKFLOW_COMPONENT_MODELS = {"workflow-prepare": WorkflowPrepareBlock}
WORKFLOW_COMPONENT_CATALOG = (
    {
        "type": "workflow-prepare",
        "terminology_key": "workflow-prepare",
        "label": "Workflow Prepare",
        "order": 1,
        "icon_key": "play-fill",
        "editor_key": "workflow_prepare",
    },
)


__all__ = [
    "DEFAULT_WORKFLOW_PREPARE_SOURCE",
    "WORKFLOW_COMPONENT_CATALOG",
    "WORKFLOW_COMPONENT_MODELS",
    "WorkflowPrepareBlock",
    "WorkflowPrepareError",
    "WorkflowPrepareInput",
    "WorkflowPrepareResult",
    "run_workflow_prepare",
]
