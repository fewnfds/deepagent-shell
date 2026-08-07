from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from agent_shell.automation.contracts import AutomationPluginBinding
from agent_shell.public_ids import default_public_id


PUBLIC_ID_PATTERN = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NODE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")


class StrictWorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowRootInterface(StrictWorkflowModel):
    kind: Literal["chat"] = "chat"
    input: Literal["messages"] = "messages"
    output: Literal["message"] = "message"


class AgentBaseSource(StrictWorkflowModel):
    kind: Literal["main-agent-profile"] = "main-agent-profile"
    id: Annotated[str, Field(min_length=1, max_length=120)]


class WorkflowAgentBase(StrictWorkflowModel):
    source: AgentBaseSource
    inherit: list[
        Literal[
            "model",
            "system-prompt",
            "skills",
            "capabilities",
            "filesystem",
        ]
    ] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_inherit_fields(self) -> "WorkflowAgentBase":
        if len(self.inherit) != len(set(self.inherit)):
            raise ValueError("AgentBase inherit fields must be unique")
        return self


class WorkflowPortRef(StrictWorkflowModel):
    node: Annotated[str, Field(min_length=1, max_length=120)]
    port: Annotated[str, Field(min_length=1, max_length=120)]


class WorkflowNode(StrictWorkflowModel):
    id: Annotated[str, Field(min_length=1, max_length=120)]
    type: Annotated[str, Field(min_length=3, max_length=200)]
    version: Literal["1.0.0"] = "1.0.0"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def valid_node_id(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("node id must use lowercase letters, digits, and hyphens")
        return value

    @field_validator("type")
    @classmethod
    def valid_node_type(cls, value: str) -> str:
        if not NODE_TYPE_PATTERN.fullmatch(value):
            raise ValueError("node type must be a dotted lowercase identifier")
        return value


class WorkflowEdge(StrictWorkflowModel):
    id: Annotated[str, Field(min_length=1, max_length=120)]
    source: WorkflowPortRef
    target: WorkflowPortRef

    @field_validator("id")
    @classmethod
    def valid_edge_id(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("edge id must use lowercase letters, digits, and hyphens")
        return value


class WorkflowPosition(StrictWorkflowModel):
    x: Annotated[float, Field(ge=-1_000_000, le=1_000_000)]
    y: Annotated[float, Field(ge=-1_000_000, le=1_000_000)]


class WorkflowDefinition(StrictWorkflowModel):
    public_id: Annotated[str, Field(min_length=10, max_length=120)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=100_000)] = ""
    schema_version: Literal[1] = 1
    enabled: bool = True
    root_interface: WorkflowRootInterface = Field(default_factory=WorkflowRootInterface)
    agent_base: WorkflowAgentBase | None = None
    preparation: list[AutomationPluginBinding] = Field(default_factory=list, max_length=100)
    nodes: list[WorkflowNode] = Field(min_length=2, max_length=100)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=300)
    layout: dict[str, WorkflowPosition] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def default_public_id_from_name(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value.get("public_id"):
            value = dict(value)
            value["public_id"] = default_public_id("workflow", str(value.get("name", "")))
        return value

    @field_validator("public_id")
    @classmethod
    def valid_public_id(cls, value: str) -> str:
        if not PUBLIC_ID_PATTERN.fullmatch(value) or not value.startswith("workflow-"):
            raise ValueError(
                "Workflow public_id must start with workflow- and contain only lowercase words separated by hyphens"
            )
        return value


class WorkflowRecord(WorkflowDefinition):
    id: Annotated[str, Field(min_length=1, max_length=120)]
    revision: Annotated[int, Field(ge=1)]


class WorkflowSaveRequest(WorkflowDefinition):
    revision: Annotated[int, Field(ge=1)] | None = None


class WorkflowDraftValidationRequest(StrictWorkflowModel):
    workflow: WorkflowDefinition


def workflow_payload(definition: WorkflowDefinition) -> dict[str, Any]:
    return definition.model_dump(mode="json")
