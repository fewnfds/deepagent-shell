from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport
from agent_shell.workflow.catalog import BUILTIN_NODE_CATALOG, NodeDefinition, NodeRegistry
from agent_shell.workflow.contracts import WorkflowDefinition


WorkflowLookup = Callable[[str], dict[str, Any] | None]
AgentLookup = Callable[[str], dict[str, Any] | None]


class WorkflowValidator:
    """Validate a fixed graph before persistence or compilation.

    Validation describes topology and references; it never executes user code
    and never becomes a second scheduler.
    """

    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup | None = None,
        agent_lookup: AgentLookup | None = None,
        node_catalog: Mapping[str, NodeDefinition] | None = None,
        node_registry: NodeRegistry | None = None,
        max_nested_depth: int = 8,
    ) -> None:
        self._workflow_lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._catalog = dict(node_catalog or ({item.type: item for item in node_registry.all()} if node_registry else BUILTIN_NODE_CATALOG))
        self._max_nested_depth = max_nested_depth

    @staticmethod
    def _issue(code: str, path: str, message: str) -> ValidationIssue:
        return ValidationIssue(
            code=code,
            scope="workflow",
            path=path,
            message=message,
            message_key="validation.issue.contract.invalidValue",
        )

    def validate_payload(
        self,
        payload: object,
        *,
        stage: str = "workflow_save",
        owner_id: str = "",
    ) -> tuple[ValidationReport, WorkflowDefinition | None]:
        try:
            definition = WorkflowDefinition.model_validate(payload)
        except ValidationError as exc:
            return report_from_validation_error(
                exc, stage=stage, scope="workflow", owner_id=owner_id, owner_type="workflow"
            ), None
        issues = self._graph_issues(definition)
        if not issues and self._workflow_lookup is not None:
            issues.extend(self._reference_issues(definition, owner_id=owner_id))
        report = ValidationReport(stage=stage, issues=tuple(issues))
        return report, definition if report.valid else None

    def _graph_issues(self, workflow: WorkflowDefinition) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        nodes: dict[str, Any] = {}
        definitions: dict[str, NodeDefinition] = {}
        for index, node in enumerate(workflow.nodes):
            if node.id in nodes:
                issues.append(self._issue("workflow.node_id_duplicate", f"nodes[{index}].id", "Workflow node ids must be unique."))
                continue
            nodes[node.id] = node
            definition = self._catalog.get(node.type)
            if definition is None or definition.version != node.version:
                issues.append(self._issue("workflow.node_type_unknown", f"nodes[{index}].type", "The Workflow node type or version is unavailable."))
                continue
            definitions[node.id] = definition
            for error in Draft202012Validator(definition.config_schema).iter_errors(node.config):
                path = ".".join(str(part) for part in error.absolute_path)
                issues.append(self._issue("workflow.node_config_invalid", f"nodes[{index}].config{('.' + path) if path else ''}", error.message))
            if definition.execution_kind == "agent":
                profile_id = node.config.get("profile_id")
                if not isinstance(profile_id, str) or not profile_id:
                    issues.append(self._issue("workflow.agent_reference_required", f"nodes[{index}].config.profile_id", "Agent nodes require a Main Agent Profile."))
                elif self._agent_lookup is not None and self._agent_lookup(profile_id) is None:
                    issues.append(self._issue("workflow.agent_reference_missing", f"nodes[{index}].config.profile_id", "The referenced Main Agent Profile does not exist."))

        incoming_control: dict[str, int] = defaultdict(int)
        incoming_control_edges: dict[str, list[Any]] = defaultdict(list)
        adjacency: dict[str, set[str]] = defaultdict(set)
        incoming_data: dict[tuple[str, str], int] = defaultdict(int)
        edge_keys: set[tuple[str, str, str, str, str]] = set()
        for index, edge in enumerate(workflow.edges):
            source = nodes.get(edge.source.node)
            target = nodes.get(edge.target.node)
            if source is None:
                issues.append(self._issue("workflow.edge_source_missing", f"edges[{index}].source.node", "The source node does not exist."))
                continue
            if target is None:
                issues.append(self._issue("workflow.edge_target_missing", f"edges[{index}].target.node", "The target node does not exist."))
                continue
            source_definition = definitions.get(source.id)
            target_definition = definitions.get(target.id)
            if source_definition is None or target_definition is None:
                continue
            source_port = next((p for p in source_definition.output_ports if p.name == edge.source.port), None)
            target_port = next((p for p in target_definition.input_ports if p.name == edge.target.port), None)
            if source_port is None and edge.kind == "data":
                issues.append(self._issue("workflow.source_port_missing", f"edges[{index}].source.port", "The source output port does not exist."))
                continue
            if target_port is None and edge.kind == "data":
                issues.append(self._issue("workflow.target_port_missing", f"edges[{index}].target.port", "The target input port does not exist."))
                continue
            key = (edge.kind, edge.source.node, edge.source.port, edge.target.node, edge.target.port)
            if key in edge_keys:
                issues.append(self._issue("workflow.edge_duplicate", f"edges[{index}]", "The same graph connection is declared more than once."))
                continue
            edge_keys.add(key)
            if edge.kind == "data":
                if source_port is None or target_port is None:
                    continue
                if source_port.value_type != target_port.value_type:
                    issues.append(self._issue("workflow.port_type_mismatch", f"edges[{index}]", "The connected data ports have incompatible value types."))
                incoming_data[(target.id, target_port.name)] += 1
                if target_port.cardinality == "one" and incoming_data[(target.id, target_port.name)] > 1:
                    issues.append(self._issue("workflow.port_cardinality_exceeded", f"edges[{index}].target.port", "A single-value input port cannot have multiple data connections."))
            if edge.condition is not None and edge.kind != "control":
                issues.append(self._issue("workflow.edge_condition_invalid", f"edges[{index}].condition", "Only control edges may have a condition."))
            if edge.kind == "control":
                adjacency[source.id].add(target.id)
                incoming_control[target.id] += 1
                incoming_control_edges[target.id].append(edge)

        for index, item in enumerate(workflow.interface.inputs):
            node = nodes.get(item.target.node)
            definition = definitions.get(item.target.node)
            port = next((p for p in definition.input_ports if p.name == item.target.port), None) if definition else None
            if node is None or port is None:
                issues.append(self._issue("workflow.interface_input_target_missing", f"interface.inputs[{index}].target", "The graph input target port does not exist."))
            elif port.value_type != item.value_type:
                issues.append(self._issue("workflow.interface_input_type_mismatch", f"interface.inputs[{index}]", "The graph input type does not match its target port."))
        for index, item in enumerate(workflow.interface.outputs):
            definition = definitions.get(item.source.node)
            port = next((p for p in definition.output_ports if p.name == item.source.port), None) if definition else None
            if port is None:
                issues.append(self._issue("workflow.interface_output_source_missing", f"interface.outputs[{index}].source", "The graph output source port does not exist."))
            elif port.value_type != item.value_type:
                issues.append(self._issue("workflow.interface_output_type_mismatch", f"interface.outputs[{index}]", "The graph output type does not match its source port."))

        roots = set(workflow.entry_nodes)
        for index, node_id in enumerate(workflow.entry_nodes):
            if node_id not in nodes:
                issues.append(self._issue("workflow.entry_node_missing", f"entry_nodes[{index}]", "The graph entry node does not exist."))
        for node_id, definition in definitions.items():
            if definition.control_mode == "command" and not incoming_control_edges[node_id]:
                issues.append(self._issue("workflow.command_destinations_required", f"nodes.{node_id}", "A Command node requires at least one declared control destination."))
            if definition.execution_kind != "join":
                continue
            edges = incoming_control_edges[node_id]
            if len(edges) < 2:
                issues.append(self._issue("workflow.join_inputs_required", f"nodes.{node_id}", "A Join node requires at least two incoming control edges."))
            if any(edge.condition is not None for edge in edges):
                issues.append(self._issue("workflow.join_condition_invalid", f"nodes.{node_id}", "Join input edges must be unconditional."))
            if node_id in roots:
                issues.append(self._issue("workflow.join_entry_invalid", f"entry_nodes.{node_id}", "A Join node cannot be a graph entry."))
        reachable: set[str] = set(roots)
        queue = deque(roots)
        while queue:
            node_id = queue.popleft()
            for child in adjacency[node_id]:
                if child not in reachable:
                    reachable.add(child)
                    queue.append(child)
        for node_id in nodes:
            if node_id not in reachable:
                issues.append(self._issue("workflow.node_unreachable", f"nodes.{node_id}", "Every node must be reachable from a control entry node."))
        return issues

    def _reference_issues(self, workflow: WorkflowDefinition, *, owner_id: str) -> list[ValidationIssue]:
        if self._workflow_lookup is None:
            return []
        issues: list[ValidationIssue] = []

        def visit(definition: WorkflowDefinition, active: tuple[str, ...], depth: int, path: str) -> None:
            for index, node in enumerate(definition.nodes):
                kind = self._catalog.get(node.type)
                if kind is None or kind.execution_kind != "workflow":
                    continue
                child_id = node.config.get("graph_id")
                node_path = f"{path}nodes[{index}].config.graph_id"
                if not isinstance(child_id, str) or not child_id:
                    continue
                if child_id == owner_id or child_id in active:
                    issues.append(self._issue("workflow.reference_cycle", node_path, "Graph references may not form a cycle."))
                    continue
                if depth >= self._max_nested_depth:
                    issues.append(self._issue("workflow.nesting_too_deep", node_path, "Graph nesting exceeds the configured limit."))
                    continue
                child = self._workflow_lookup(child_id)
                if child is None:
                    issues.append(self._issue("workflow.reference_missing", node_path, "The referenced Graph does not exist."))
                    continue
                try:
                    child_definition = WorkflowDefinition.model_validate({k: v for k, v in child.items() if k not in {"id", "revision"}})
                except ValidationError:
                    issues.append(self._issue("workflow.reference_invalid", node_path, "The referenced Graph is invalid."))
                    continue
                visit(child_definition, (*active, child_id), depth + 1, f"{node_path}.graph.")

        visit(workflow, (owner_id,), 1, "")
        return issues
