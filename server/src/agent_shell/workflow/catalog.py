from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_shell.workflow.contracts import Cardinality, ValueType


@dataclass(frozen=True, slots=True)
class PortDefinition:
    name: str
    value_type: ValueType
    required: bool = True
    cardinality: Cardinality = "one"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value_type": self.value_type,
            "required": self.required,
            "cardinality": self.cardinality,
        }


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    type: str
    version: str
    title: str
    input_ports: tuple[PortDefinition, ...]
    output_ports: tuple[PortDefinition, ...]
    config_schema: Mapping[str, Any]
    execution_kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "title": self.title,
            "input_ports": [port.as_dict() for port in self.input_ports],
            "output_ports": [port.as_dict() for port in self.output_ports],
            "config_schema": dict(self.config_schema),
            "execution_kind": self.execution_kind,
        }


BUILTIN_NODE_DEFINITIONS: tuple[NodeDefinition, ...] = (
    NodeDefinition(
        type="builtin.agent.call",
        version="1.0.0",
        title="Agent",
        input_ports=(PortDefinition("messages", "messages"),),
        output_ports=(
            PortDefinition("response", "text"),
            PortDefinition("messages", "messages"),
        ),
        config_schema={
            "type": "object",
            "properties": {"agent_id": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        execution_kind="agent",
    ),
    NodeDefinition(
        type="builtin.tool.call",
        version="1.0.0",
        title="Tool",
        input_ports=(PortDefinition("arguments", "json", required=False),),
        output_ports=(PortDefinition("result", "json"),),
        config_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "minLength": 1},
                "arguments": {"type": "object"},
            },
            "required": ["tool_name"],
            "additionalProperties": False,
        },
        execution_kind="tool",
    ),
    NodeDefinition(
        type="builtin.workflow.call",
        version="1.0.0",
        title="Workflow",
        input_ports=(PortDefinition("input", "json"),),
        output_ports=(PortDefinition("output", "json"),),
        config_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string", "minLength": 1}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        execution_kind="workflow",
    ),
    NodeDefinition(
        type="builtin.value",
        version="1.0.0",
        title="Value",
        input_ports=(),
        output_ports=(PortDefinition("value", "json"),),
        config_schema={
            "type": "object",
            "properties": {"value": {}},
            "required": ["value"],
            "additionalProperties": False,
        },
        execution_kind="value",
    ),
    NodeDefinition(
        type="builtin.pass",
        version="1.0.0",
        title="Pass",
        input_ports=(PortDefinition("value", "json"),),
        output_ports=(PortDefinition("value", "json"),),
        config_schema={"type": "object", "additionalProperties": False},
        execution_kind="pass",
    ),
)

BUILTIN_NODE_CATALOG = {item.type: item for item in BUILTIN_NODE_DEFINITIONS}


class NodeRegistry:
    """Immutable builtin catalog owner; plugin contributions attach at construction time."""

    def __init__(self, definitions: Mapping[str, NodeDefinition] | None = None) -> None:
        self._definitions = dict(definitions or BUILTIN_NODE_CATALOG)

    def get(self, node_type: str) -> NodeDefinition | None:
        return self._definitions.get(node_type)

    def all(self) -> tuple[NodeDefinition, ...]:
        return tuple(self._definitions.values())


def public_node_catalog(registry: NodeRegistry | None = None) -> dict[str, Any]:
    active = registry or NodeRegistry()
    return {
        "api_version": 2,
        "nodes": [definition.as_dict() for definition in active.all()],
    }
