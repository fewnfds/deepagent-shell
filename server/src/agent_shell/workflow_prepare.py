from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
)

from agent_shell.condition_router import ConditionRouterBlock
from agent_shell.python_packages.contracts import PythonPackageReference
from agent_shell.task_dispatcher import TaskDispatcherBlock
from agent_shell.workflow_event_output import WorkflowEventOutputBlock


WorkflowPrepareCallable = Callable[[dict[str, Any]], Awaitable[Any]]


class WorkflowPrepareBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    python_package: PythonPackageReference


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
    prepare: WorkflowPrepareCallable,
    *,
    input_value: dict[str, Any],
) -> WorkflowPrepareResult:
    try:
        prepared_input = WorkflowPrepareInput.model_validate(input_value).model_dump(
            mode="json"
        )
        value = await prepare(input=deepcopy(prepared_input))
        return WorkflowPrepareResult.model_validate(value)
    except Exception as exc:
        raise WorkflowPrepareError("workflow prepare failed") from exc


WORKFLOW_COMPONENT_MODELS = {
    "workflow-prepare": WorkflowPrepareBlock,
    "workflow-event-output": WorkflowEventOutputBlock,
    "condition-router": ConditionRouterBlock,
    "task-dispatcher": TaskDispatcherBlock,
}
WORKFLOW_COMPONENT_CATALOG = (
    {
        "type": "workflow-prepare",
        "terminology_key": "workflow-prepare",
        "label": "Prepare",
        "order": 1,
        "icon_key": "play-fill",
        "editor_key": "workflow_prepare",
    },
    {
        "type": "workflow-event-output",
        "terminology_key": "workflow-event-output",
        "label": "Event Output",
        "order": 2,
        "icon_key": "braces",
        "editor_key": "workflow_event_output",
    },
    {
        "type": "condition-router",
        "terminology_key": "condition-router",
        "label": "Condition Router",
        "order": 3,
        "icon_key": "circle-half",
        "editor_key": "condition_router",
    },
    {
        "type": "task-dispatcher",
        "terminology_key": "task-dispatcher",
        "label": "Task Dispatcher",
        "order": 4,
        "icon_key": "boxes",
        "editor_key": "task_dispatcher",
    },
)


__all__ = [
    "WORKFLOW_COMPONENT_CATALOG",
    "WORKFLOW_COMPONENT_MODELS",
    "WorkflowPrepareBlock",
    "WorkflowPrepareCallable",
    "WorkflowPrepareError",
    "WorkflowPrepareInput",
    "WorkflowPrepareResult",
    "run_workflow_prepare",
]
