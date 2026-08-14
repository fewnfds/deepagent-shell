from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
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
from agent_shell.workflow.contracts import WORKFLOW_STATE_CONTRACT


EndpointId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
    ),
]
DisplayText = Annotated[str, StringConstraints(strip_whitespace=True)]
PythonSource = Annotated[str, StringConstraints(strip_whitespace=False)]

DEFAULT_WORKFLOW_COMPONENT_CONFIG_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
DEFAULT_WORKFLOW_COMPONENT_SOURCE = (
    "async def run(input):\n"
    "    return {\"update\": {}, \"route\": \"next\"}\n"
)


class WorkflowComponentInputEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: EndpointId
    label: DisplayText = Field(default="", max_length=120)
    activation: Literal["any", "all"] = "any"
    accepted_edge_types: list[Literal["normal", "conditional"]] = Field(
        default_factory=lambda: ["normal", "conditional"],
        min_length=1,
        max_length=2,
    )
    max_connections: int | None = Field(default=None, ge=1)

    @field_validator("accepted_edge_types")
    @classmethod
    def unique_edge_types(
        cls, values: list[Literal["normal", "conditional"]]
    ) -> list[Literal["normal", "conditional"]]:
        if len(values) != len(set(values)):
            raise ValueError("accepted edge types must be unique")
        return values


class WorkflowComponentOutputEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: EndpointId
    label: DisplayText = Field(default="", max_length=120)
    edge_type: Literal["normal", "conditional"] = "conditional"
    max_connections: int | None = Field(default=1, ge=1)


class WorkflowComponentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: DisplayText = Field(min_length=1, max_length=120)
    description: DisplayText = Field(default="", max_length=2048)
    runtime_kind: Literal["python-command"] = "python-command"
    state_contract: Literal["agent-shell.workflow.agent-invocations.v1"] = (
        WORKFLOW_STATE_CONTRACT
    )
    input_endpoints: list[WorkflowComponentInputEndpoint] = Field(
        default_factory=lambda: [WorkflowComponentInputEndpoint(id="in")],
        min_length=1,
        max_length=32,
    )
    output_endpoints: list[WorkflowComponentOutputEndpoint] = Field(
        default_factory=lambda: [WorkflowComponentOutputEndpoint(id="next")],
        min_length=1,
        max_length=32,
    )
    config_schema: dict[str, JsonValue] = Field(
        default_factory=lambda: dict(DEFAULT_WORKFLOW_COMPONENT_CONFIG_SCHEMA)
    )
    python_source: PythonSource = Field(
        default=DEFAULT_WORKFLOW_COMPONENT_SOURCE,
        max_length=100_000,
    )
    python_requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("python_requirements")
    @classmethod
    def validate_python_requirements(cls, values: list[str]) -> list[str]:
        return list(parse_python_requirements(values).values)

    @model_validator(mode="after")
    def validate_definition(self) -> "WorkflowComponentDefinition":
        for endpoints, label in (
            (self.input_endpoints, "input"),
            (self.output_endpoints, "output"),
        ):
            identities = [endpoint.id for endpoint in endpoints]
            if len(identities) != len(set(identities)):
                raise ValueError(f"{label} endpoint IDs must be unique")
        if self.config_schema.get("type") != "object":
            raise ValueError("the instance config schema must have type=object")
        try:
            Draft202012Validator.check_schema(self.config_schema)
        except SchemaError as exc:
            raise ValueError("the instance config schema is invalid") from exc
        validate_module_function(self.python_source, "run", asynchronous=True)
        return self


class WorkflowComponentInstance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    definition_id: UUID
    name: DisplayText = Field(min_length=1, max_length=120)
    description: DisplayText = Field(default="", max_length=2048)
    config: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowComponentConfigIssue:
    path: tuple[str, ...]
    keyword: str


def validate_workflow_component_config(
    schema: dict[str, Any],
    config: object,
) -> WorkflowComponentConfigIssue | None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(config),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return None
    error = errors[0]
    return WorkflowComponentConfigIssue(
        path=tuple(str(part) for part in error.absolute_path),
        keyword=str(error.validator or "schema"),
    )


__all__ = [
    "DEFAULT_WORKFLOW_COMPONENT_CONFIG_SCHEMA",
    "DEFAULT_WORKFLOW_COMPONENT_SOURCE",
    "WorkflowComponentConfigIssue",
    "WorkflowComponentDefinition",
    "WorkflowComponentInputEndpoint",
    "WorkflowComponentInstance",
    "WorkflowComponentOutputEndpoint",
    "validate_workflow_component_config",
]
