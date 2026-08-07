from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agent_shell.workflow.contracts import Cardinality, ValueType


PortValueType = ValueType | str


@dataclass(frozen=True, slots=True)
class PortDefinition:
    name: str
    value_type: PortValueType
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
    description: str
    input_ports: tuple[PortDefinition, ...]
    output_ports: tuple[PortDefinition, ...]
    config_schema: Mapping[str, Any]
    execution_kind: str
    plugin_id: str | None = None
    entrypoint: str | None = None
    control_mode: str = "signal"

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "input_ports": [port.as_dict() for port in self.input_ports],
            "output_ports": [port.as_dict() for port in self.output_ports],
            "config_schema": dict(self.config_schema),
            "execution_kind": self.execution_kind,
            "plugin_id": self.plugin_id,
            "entrypoint": self.entrypoint,
            "control_mode": self.control_mode,
        }


BUILTIN_NODE_DEFINITIONS: tuple[NodeDefinition, ...] = (
    NodeDefinition(
        type="builtin.value",
        version="1.0.0",
        title="Value",
        description="Publish a small JSON value to the graph.",
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
        description="Pass a connected value to the next node.",
        input_ports=(PortDefinition("value", "json"),),
        output_ports=(PortDefinition("value", "json"),),
        config_schema={"type": "object", "additionalProperties": False},
        execution_kind="pass",
    ),
    NodeDefinition(
        type="builtin.state.update",
        version="1.0.0",
        title="Shared State Update",
        description="Write a value into the user-controlled shared State object.",
        input_ports=(PortDefinition("value", "json", required=False),),
        output_ports=(PortDefinition("status", "control"),),
        config_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "operation": {"type": "string", "enum": ["set", "append", "merge"]},
                "value": {},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        execution_kind="state_update",
    ),
    NodeDefinition(
        type="builtin.router",
        version="1.0.0",
        title="Router",
        description="Read one shared State path and publish a control signal for conditional edges.",
        input_ports=(),
        output_ports=(PortDefinition("status", "control"),),
        config_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 500},
                "cases": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "pattern": "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"},
                },
                "default": {"type": "string", "pattern": "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"},
            },
            "required": ["path", "cases", "default"],
            "additionalProperties": False,
        },
        execution_kind="router",
    ),
    NodeDefinition(
        type="builtin.join",
        version="1.0.0",
        title="Join",
        description="Continue after every declared incoming control branch has completed.",
        input_ports=(),
        output_ports=(PortDefinition("status", "control"),),
        config_schema={"type": "object", "additionalProperties": False},
        execution_kind="join",
    ),
    NodeDefinition(
        type="builtin.agent",
        version="1.0.0",
        title="Main Agent Profile",
        description="Run a preconfigured Main Agent Profile; its hooks decide State and prompt mapping.",
        input_ports=(PortDefinition("messages", "messages", required=False),),
        output_ports=(
            PortDefinition("response", "text", required=False),
            PortDefinition("messages", "messages", required=False),
            PortDefinition("status", "control"),
        ),
        config_schema={
            "type": "object",
            "properties": {
                "profile_id": {"type": "string", "minLength": 1},
                "timeout_seconds": {"type": "number", "minimum": 0.1, "maximum": 86_400},
                "max_attempts": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["profile_id"],
            "additionalProperties": False,
        },
        execution_kind="agent",
    ),
    NodeDefinition(
        type="builtin.tool",
        version="1.0.0",
        title="Tool",
        description="Call a registered deterministic tool.",
        input_ports=(PortDefinition("arguments", "json", required=False),),
        output_ports=(PortDefinition("result", "json"), PortDefinition("status", "control")),
        config_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "minLength": 1},
                "arguments": {"type": "object"},
                "timeout_seconds": {"type": "number", "minimum": 0.1, "maximum": 86_400},
                "max_attempts": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["tool_name"],
            "additionalProperties": False,
        },
        execution_kind="tool",
    ),
    NodeDefinition(
        type="builtin.workflow",
        version="1.0.0",
        title="Graph Call",
        description="Call another saved Graph through a typed boundary.",
        input_ports=(PortDefinition("input", "json", required=False),),
        output_ports=(PortDefinition("output", "json"), PortDefinition("status", "control")),
        config_schema={
            "type": "object",
            "properties": {"graph_id": {"type": "string", "minLength": 1}},
            "required": ["graph_id"],
            "additionalProperties": False,
        },
        execution_kind="workflow",
    ),
)

BUILTIN_NODE_CATALOG = {item.type: item for item in BUILTIN_NODE_DEFINITIONS}


class NodeRegistry:
    """Immutable catalog assembled from builtin and enabled plugin descriptors."""

    def __init__(self, definitions: Mapping[str, NodeDefinition] | None = None) -> None:
        self._definitions = dict(definitions or BUILTIN_NODE_CATALOG)

    def get(self, node_type: str, version: str | None = None) -> NodeDefinition | None:
        definition = self._definitions.get(node_type)
        if definition is None or version is not None and definition.version != version:
            return None
        return definition

    def all(self) -> tuple[NodeDefinition, ...]:
        return tuple(self._definitions.values())


def public_node_catalog(registry: NodeRegistry | None = None) -> dict[str, Any]:
    active = registry or NodeRegistry()
    return {
        "api_version": 3,
        "nodes": [definition.as_dict() for definition in active.all()],
    }


def scan_workflow_node_registry(directory: Any, *, runtime_root: Any = None) -> NodeRegistry:
    """Merge workflow-node contributions from the existing Plugin source tree.

    Scanning validates manifests and Python signatures only; importing and
    executing a contribution remains request-local and happens in the
    compiler's node runtime.
    """
    from agent_shell.automation.scripts import scan_automation_scripts

    definitions = dict(BUILTIN_NODE_CATALOG)
    catalog = scan_automation_scripts(directory, runtime_root=runtime_root)
    for plugin in catalog.get("catalog", []):
        if not isinstance(plugin, dict):
            continue
        plugin_id = str(plugin.get("id") or "")
        for contribution in plugin.get("workflow_nodes", []) or []:
            if not isinstance(contribution, dict):
                continue
            node_type = str(contribution.get("type") or "")
            ports_in = tuple(
                PortDefinition(
                    str(item.get("name")),
                    str(item.get("value_type", "json")),
                    bool(item.get("required", True)),
                    str(item.get("cardinality", "one")),
                )
                for item in contribution.get("input_ports", [])
                if isinstance(item, dict)
            )
            ports_out = tuple(
                PortDefinition(
                    str(item.get("name")),
                    str(item.get("value_type", "json")),
                    bool(item.get("required", True)),
                    str(item.get("cardinality", "one")),
                )
                for item in contribution.get("output_ports", [])
                if isinstance(item, dict)
            )
            if node_type and node_type not in definitions:
                definitions[node_type] = NodeDefinition(
                    type=node_type,
                    version=str(contribution.get("version", "1.0.0")),
                    title=str(contribution.get("title", node_type)),
                    description=str(contribution.get("description", "")),
                    input_ports=ports_in,
                    output_ports=ports_out,
                    config_schema=dict(contribution.get("config_schema") or {"type": "object"}),
                    execution_kind="plugin",
                    plugin_id=plugin_id,
                    entrypoint=str(contribution.get("entrypoint", "run")),
                    control_mode=str(contribution.get("control_mode", "signal")),
                )
    return NodeRegistry(definitions)
