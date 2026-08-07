from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_shell.automation.contracts import AutomationPluginBinding


NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NODE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
PORT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

ValueType = Literal[
    "messages",
    "text",
    "json",
    "boolean",
    "list",
    "artifact",
    "artifact-list",
]
Cardinality = Literal["one", "many"]


class StrictWorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowPortRef(StrictWorkflowModel):
    node: Annotated[str, Field(min_length=1, max_length=120)]
    port: Annotated[str, Field(min_length=1, max_length=120)]

    @field_validator("node")
    @classmethod
    def valid_node(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("node id must use lowercase letters, digits, and hyphens")
        return value

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: str) -> str:
        if not PORT_NAME_PATTERN.fullmatch(value):
            raise ValueError("port name must use lowercase letters, digits, and hyphens")
        return value


class WorkflowInterfaceInput(StrictWorkflowModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    value_type: ValueType
    required: bool = True
    cardinality: Cardinality = "one"
    target: WorkflowPortRef

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not PORT_NAME_PATTERN.fullmatch(value):
            raise ValueError("interface input name must use lowercase letters, digits, and hyphens")
        return value


class WorkflowInterfaceOutput(StrictWorkflowModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    value_type: ValueType
    required: bool = True
    source: WorkflowPortRef

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not PORT_NAME_PATTERN.fullmatch(value):
            raise ValueError("interface output name must use lowercase letters, digits, and hyphens")
        return value


class WorkflowInterface(StrictWorkflowModel):
    inputs: list[WorkflowInterfaceInput] = Field(default_factory=list, max_length=32)
    outputs: list[WorkflowInterfaceOutput] = Field(default_factory=list, max_length=32)


class WorkflowNode(StrictWorkflowModel):
    id: Annotated[str, Field(min_length=1, max_length=120)]
    type: Annotated[str, Field(min_length=3, max_length=200)]
    version: Annotated[str, Field(min_length=1, max_length=32)] = "1.0.0"
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
            raise ValueError("node type must be a dotted or hyphenated lowercase identifier")
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
    """Persisted graph definition; resource identity lives outside the payload."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=100_000)] = ""
    schema_version: Literal[2] = 2
    enabled: bool = True
    interface: WorkflowInterface
    agent_base_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    setup: list[AutomationPluginBinding] = Field(default_factory=list, max_length=100)
    nodes: list[WorkflowNode] = Field(min_length=1, max_length=200)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=600)
    layout: dict[str, WorkflowPosition] = Field(default_factory=dict)


class WorkflowRecord(WorkflowDefinition):
    id: Annotated[str, Field(min_length=1, max_length=120)]
    revision: Annotated[int, Field(ge=1)]


class WorkflowSaveRequest(WorkflowDefinition):
    revision: Annotated[int, Field(ge=1)] | None = None


class WorkflowDraftValidationRequest(StrictWorkflowModel):
    workflow: WorkflowDefinition


def workflow_payload(definition: WorkflowDefinition) -> dict[str, Any]:
    return definition.model_dump(mode="json")
