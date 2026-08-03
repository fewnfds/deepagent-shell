from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WorkflowName = Annotated[str, Field(min_length=1, max_length=120)]
WorkflowReference = Annotated[str, Field(max_length=120)]
RequiredScriptId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$"),
]


class AutomationNode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    script_id: RequiredScriptId
    config: dict[str, Any] = Field(default_factory=dict)


class HookNodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_prepare: list[AutomationNode] = Field(default_factory=list, max_length=100)
    subagent_before_invoke: list[AutomationNode] = Field(
        default_factory=list, max_length=100
    )
    request_end: list[AutomationNode] = Field(default_factory=list, max_length=100)


class HookWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: WorkflowName
    hooks: HookNodes = Field(default_factory=HookNodes)

    @model_validator(mode="after")
    def require_node(self) -> "HookWorkflow":
        if not (
            self.hooks.request_prepare
            or self.hooks.subagent_before_invoke
            or self.hooks.request_end
        ):
            raise ValueError("an event workflow requires at least one script node")
        return self


class LifecycleWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: WorkflowName
    interval_seconds: float = Field(ge=0.1, le=86_400)
    nodes: list[AutomationNode] = Field(min_length=1, max_length=100)


class PrimaryAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hook_workflow_id: WorkflowReference = ""
    lifecycle_workflow_id: WorkflowReference = ""


class WorkflowOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: Literal["inherit", "replace", "disabled"] = "inherit"
    workflow_id: WorkflowReference = ""

    @model_validator(mode="after")
    def validate_selection(self) -> "WorkflowOverride":
        if self.mode == "replace" and not self.workflow_id:
            raise ValueError("replace mode requires a workflow_id")
        if self.mode != "replace" and self.workflow_id:
            raise ValueError("only replace mode may contain a workflow_id")
        return self


class SubagentAutomation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    hook_workflow: WorkflowOverride = Field(default_factory=WorkflowOverride)
    lifecycle_workflow: WorkflowOverride = Field(default_factory=WorkflowOverride)


WORKFLOW_MODELS = {
    "hook-workflow": HookWorkflow,
    "lifecycle-workflow": LifecycleWorkflow,
}


def validate_workflow_payload(workflow_type: str, payload: dict[str, Any]) -> dict:
    model = WORKFLOW_MODELS[workflow_type]
    return model.model_validate(payload).model_dump(mode="json")

