from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmptyNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentNodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_agent_id: UUID
    # Reserved execution policy for LangGraph's deferred node scheduling.
    defer: bool = False


@dataclass(frozen=True, slots=True)
class NodeHandleSpec:
    id: str
    edge_type: str = "normal"
    # None follows Vue Flow/LangGraph semantics: the control handle is not
    # cardinality-limited by the catalog. Graph topology remains authoritative.
    max_connections: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": "control",
            "edge_type": self.edge_type,
            "max_connections": self.max_connections,
        }


@dataclass(frozen=True, slots=True)
class NodeTypeSpec:
    type: str
    type_version: int
    runtime_kind: Literal["graph_entry", "graph_exit", "agent_wrapper"]
    title_key: str
    description_key: str
    config_model: type[BaseModel]
    input_handles: tuple[NodeHandleSpec, ...]
    output_handles: tuple[NodeHandleSpec, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "type_version": self.type_version,
            "runtime_kind": self.runtime_kind,
            "title_key": self.title_key,
            "description_key": self.description_key,
            "config_schema": self.config_model.model_json_schema(),
            "input_handles": [item.as_dict() for item in self.input_handles],
            "output_handles": [item.as_dict() for item in self.output_handles],
        }


_IN = (NodeHandleSpec("in"),)
_NEXT = (NodeHandleSpec("next"),)

NODE_CATALOG: tuple[NodeTypeSpec, ...] = (
    NodeTypeSpec(
        type="start",
        type_version=1,
        runtime_kind="graph_entry",
        title_key="workflow.nodes.start.title",
        description_key="workflow.nodes.start.description",
        config_model=EmptyNodeConfig,
        input_handles=(),
        output_handles=_NEXT,
    ),
    NodeTypeSpec(
        type="agent",
        type_version=1,
        runtime_kind="agent_wrapper",
        title_key="workflow.nodes.agent.title",
        description_key="workflow.nodes.agent.description",
        config_model=AgentNodeConfig,
        input_handles=_IN,
        output_handles=_NEXT,
    ),
    NodeTypeSpec(
        type="end",
        type_version=1,
        runtime_kind="graph_exit",
        title_key="workflow.nodes.end.title",
        description_key="workflow.nodes.end.description",
        config_model=EmptyNodeConfig,
        input_handles=_IN,
        output_handles=(),
    ),
)

_NODE_TYPES = {(item.type, item.type_version): item for item in NODE_CATALOG}
_NODE_VERSIONS = {
    item.type: frozenset(
        candidate.type_version for candidate in NODE_CATALOG if candidate.type == item.type
    )
    for item in NODE_CATALOG
}


def node_type_spec(node_type: str, type_version: int) -> NodeTypeSpec | None:
    return _NODE_TYPES.get((node_type, type_version))


def supported_node_versions(node_type: str) -> frozenset[int] | None:
    return _NODE_VERSIONS.get(node_type)


def node_catalog_payload() -> list[dict[str, object]]:
    return [item.as_dict() for item in NODE_CATALOG]


__all__ = [
    "AgentNodeConfig",
    "EmptyNodeConfig",
    "NODE_CATALOG",
    "NodeHandleSpec",
    "NodeTypeSpec",
    "node_catalog_payload",
    "node_type_spec",
    "supported_node_versions",
]
