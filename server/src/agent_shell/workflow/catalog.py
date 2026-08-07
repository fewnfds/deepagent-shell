from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PortDefinition:
    name: str
    data_type: str


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    type: str
    version: str
    title: str
    input_ports: tuple[PortDefinition, ...]
    output_ports: tuple[PortDefinition, ...]
    config_schema: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "title": self.title,
            "input_ports": [vars(port) for port in self.input_ports],
            "output_ports": [vars(port) for port in self.output_ports],
            "config_schema": self.config_schema,
        }


MESSAGE = PortDefinition("messages", "messages")

BUILTIN_NODE_DEFINITIONS: tuple[NodeDefinition, ...] = (
    NodeDefinition(
        type="builtin.input.messages",
        version="1.0.0",
        title="Messages Input",
        input_ports=(),
        output_ports=(MESSAGE,),
        config_schema={"type": "object", "additionalProperties": False},
    ),
    NodeDefinition(
        type="builtin.tool.call",
        version="1.0.0",
        title="Tool",
        input_ports=(MESSAGE,),
        output_ports=(MESSAGE,),
        config_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "minLength": 1},
                "arguments": {"type": "object"},
            },
            "required": ["tool_name"],
            "additionalProperties": False,
        },
    ),
    NodeDefinition(
        type="builtin.agent.call",
        version="1.0.0",
        title="Agent",
        input_ports=(MESSAGE,),
        output_ports=(MESSAGE,),
        config_schema={
            "type": "object",
            "properties": {"agent_id": {"type": "string", "minLength": 1}},
            "required": ["agent_id"],
            "additionalProperties": False,
        },
    ),
    NodeDefinition(
        type="builtin.workflow.call",
        version="1.0.0",
        title="Workflow",
        input_ports=(MESSAGE,),
        output_ports=(MESSAGE,),
        config_schema={
            "type": "object",
            "properties": {"workflow_id": {"type": "string", "minLength": 1}},
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
    ),
    NodeDefinition(
        type="builtin.output.message",
        version="1.0.0",
        title="Message Output",
        input_ports=(MESSAGE,),
        output_ports=(),
        config_schema={"type": "object", "additionalProperties": False},
    ),
)

BUILTIN_NODE_CATALOG = {item.type: item for item in BUILTIN_NODE_DEFINITIONS}


def public_node_catalog() -> dict[str, Any]:
    return {
        "api_version": 1,
        "nodes": [definition.as_dict() for definition in BUILTIN_NODE_DEFINITIONS],
    }
