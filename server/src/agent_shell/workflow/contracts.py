from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_shell.automation.contracts import AutomationPluginBinding


# Entry-script model names are intentionally human supplied and deliberately
# small: letters (both cases) separated by hyphens.  They are not generated
# public ids and do not encode the graph kind.
ENTRY_NAME_PATTERN = re.compile(r"^[A-Za-z]+(?:-[A-Za-z]+)*$")
NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
NODE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")
PORT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

ValueType = Literal[
    "messages", "text", "json", "boolean", "list", "artifact", "artifact-list", "control"
]
Cardinality = Literal["one", "many"]
EdgeKind = Literal["control", "data"]
ControlStatus = str
UpdateOperation = Literal["set", "append", "merge"]


class StrictWorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowPortRef(StrictWorkflowModel):
    node: str = Field(min_length=1, max_length=120)
    port: str = Field(min_length=1, max_length=120)

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
    name: str = Field(min_length=1, max_length=120)
    value_type: ValueType
    required: bool = False
    cardinality: Cardinality = "one"
    target: WorkflowPortRef

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not PORT_NAME_PATTERN.fullmatch(value):
            raise ValueError("interface input name must use lowercase letters, digits, and hyphens")
        return value


class WorkflowInterfaceOutput(StrictWorkflowModel):
    name: str = Field(min_length=1, max_length=120)
    value_type: ValueType
    required: bool = False
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
    id: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=3, max_length=200)
    version: str = Field(default="1.0.0", min_length=1, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0, le=86_400)
    max_attempts: int | None = Field(default=None, ge=1, le=20)

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
            raise ValueError("node type must be a lowercase dotted identifier")
        return value


class WorkflowEdge(StrictWorkflowModel):
    id: str = Field(min_length=1, max_length=120)
    kind: EdgeKind = "control"
    source: WorkflowPortRef
    target: WorkflowPortRef
    condition: ControlStatus | None = None

    @field_validator("id")
    @classmethod
    def valid_edge_id(cls, value: str) -> str:
        if not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("edge id must use lowercase letters, digits, and hyphens")
        return value

    @field_validator("condition")
    @classmethod
    def valid_condition(cls, value: str | None) -> str | None:
        if value is not None and not NODE_ID_PATTERN.fullmatch(value):
            raise ValueError("control condition must use lowercase letters, digits, and hyphens")
        return value


class WorkflowPosition(StrictWorkflowModel):
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class WorkflowDefinition(StrictWorkflowModel):
    """The immutable, versioned Graph Definition saved by management UI."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=100_000)
    schema_version: Literal[3] = 3
    enabled: bool = True
    interface: WorkflowInterface = Field(default_factory=WorkflowInterface)
    setup: list[AutomationPluginBinding] = Field(default_factory=list, max_length=100)
    nodes: list[WorkflowNode] = Field(min_length=1, max_length=200)
    entry_nodes: list[str] = Field(min_length=1, max_length=32)
    edges: list[WorkflowEdge] = Field(default_factory=list, max_length=600)
    layout: dict[str, WorkflowPosition] = Field(default_factory=dict)
    recursion_limit: int = Field(default=100, ge=1, le=10_000)

    @field_validator("entry_nodes")
    @classmethod
    def valid_entry_nodes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("entry node ids must be unique")
        if any(not NODE_ID_PATTERN.fullmatch(item) for item in value):
            raise ValueError("entry node ids must use lowercase letters, digits, and hyphens")
        return value


GraphDefinition = WorkflowDefinition


class WorkflowRecord(WorkflowDefinition):
    id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)


class WorkflowSaveRequest(WorkflowDefinition):
    revision: int | None = Field(default=None, ge=1)


class WorkflowDraftValidationRequest(StrictWorkflowModel):
    workflow: WorkflowDefinition


class EntryScriptDefinition(StrictWorkflowModel):
    """A user-facing model name mapped to a graph and optional prepare script."""

    name: str = Field(min_length=1, max_length=120)
    graph_id: str = Field(min_length=1, max_length=120)
    source: str = Field(default="", max_length=200_000)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not ENTRY_NAME_PATTERN.fullmatch(value):
            raise ValueError("entry script name may contain only letters and hyphens")
        return value


class EntryScriptRecord(EntryScriptDefinition):
    id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)


def workflow_payload(definition: WorkflowDefinition) -> dict[str, Any]:
    return definition.model_dump(mode="json")


def entry_script_payload(definition: EntryScriptDefinition) -> dict[str, Any]:
    return definition.model_dump(mode="json")
