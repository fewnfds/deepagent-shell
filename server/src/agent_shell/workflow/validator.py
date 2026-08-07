from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport
from agent_shell.workflow.catalog import BUILTIN_NODE_CATALOG, NodeDefinition, NodeRegistry
from agent_shell.workflow.contracts import WorkflowDefinition, WorkflowPortRef


WorkflowLookup = Callable[[str], dict[str, Any] | None]
AgentLookup = Callable[[str], dict[str, Any] | None]


class WorkflowValidator:
    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup | None = None,
        agent_lookup: AgentLookup | None = None,
        node_catalog: dict[str, NodeDefinition] | None = None,
        node_registry: NodeRegistry | None = None,
        max_nested_depth: int = 8,
    ) -> None:
        self._workflow_lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._catalog = node_catalog or (node_registry.all() and {item.type: item for item in node_registry.all()}) or BUILTIN_NODE_CATALOG
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
            return (
                report_from_validation_error(
                    exc,
                    stage=stage,
                    scope="workflow",
                    owner_id=owner_id,
                    owner_type="workflow",
                ),
                None,
            )
        issues = self._graph_issues(definition)
        if not issues and self._workflow_lookup is not None:
            issues.extend(self._reference_issues(definition, owner_id=owner_id))
        if definition.agent_base_id is not None and self._agent_lookup is not None:
            if self._agent_lookup(definition.agent_base_id) is None:
                issues.append(
                    self._issue(
                        "workflow.agent_base_missing",
                        "agent_base_id",
                        "The AgentBase Main Agent profile does not exist.",
                    )
                )
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
                agent_id = node.config.get("agent_id") or workflow.agent_base_id
                if not isinstance(agent_id, str) or not agent_id:
                    issues.append(self._issue("workflow.agent_reference_required", f"nodes[{index}].config.agent_id", "Agent nodes require an Agent profile or graph AgentBase."))
                elif self._agent_lookup is not None and self._agent_lookup(agent_id) is None:
                    issues.append(self._issue("workflow.agent_reference_missing", f"nodes[{index}].config.agent_id", "The referenced Agent does not exist."))
            if definition.execution_kind == "workflow" and self._workflow_lookup is None:
                issues.append(self._issue("workflow.reference_lookup_unavailable", f"nodes[{index}].config.workflow_id", "Workflow references cannot be checked here."))

        if len(workflow.interface.inputs) == 0:
            issues.append(self._issue("workflow.interface_input_required", "interface.inputs", "A Graph must declare at least one input."))
        if len(workflow.interface.outputs) == 0:
            issues.append(self._issue("workflow.interface_output_required", "interface.outputs", "A Graph must declare at least one output."))

        adjacency: dict[str, set[str]] = defaultdict(set)
        incoming: dict[tuple[str, str], int] = defaultdict(int)
        incoming_sources: dict[tuple[str, str], list[WorkflowPortRef]] = defaultdict(list)
        edge_keys: set[tuple[str, str, str, str]] = set()
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
            source_port = next((port for port in source_definition.output_ports if port.name == edge.source.port), None)
            target_port = next((port for port in target_definition.input_ports if port.name == edge.target.port), None)
            if source_port is None:
                issues.append(self._issue("workflow.source_port_missing", f"edges[{index}].source.port", "The source output port does not exist."))
                continue
            if target_port is None:
                issues.append(self._issue("workflow.target_port_missing", f"edges[{index}].target.port", "The target input port does not exist."))
                continue
            if source_port.value_type != target_port.value_type:
                issues.append(self._issue("workflow.port_type_mismatch", f"edges[{index}]", "The connected Workflow ports have incompatible value types."))
                continue
            key = (edge.source.node, edge.source.port, edge.target.node, edge.target.port)
            if key in edge_keys:
                issues.append(self._issue("workflow.edge_duplicate", f"edges[{index}]", "The same port connection is declared more than once."))
                continue
            edge_keys.add(key)
            adjacency[edge.source.node].add(edge.target.node)
            incoming[(edge.target.node, edge.target.port)] += 1
            incoming_sources[(edge.target.node, edge.target.port)].append(edge.source)
            if target_port.cardinality == "one" and incoming[(edge.target.node, edge.target.port)] > 1:
                issues.append(self._issue("workflow.port_cardinality_exceeded", f"edges[{index}].target.port", "A single-value input port cannot have multiple connections."))

        for item in workflow.interface.inputs:
            target = nodes.get(item.target.node)
            definition = definitions.get(item.target.node)
            port = next((candidate for candidate in definition.input_ports if candidate.name == item.target.port), None) if definition else None
            if target is None or definition is None or port is None:
                issues.append(self._issue("workflow.interface_input_target_missing", f"interface.inputs[{workflow.interface.inputs.index(item)}].target", "The interface input target port does not exist."))
            elif port.value_type != item.value_type:
                issues.append(self._issue("workflow.interface_input_type_mismatch", f"interface.inputs[{workflow.interface.inputs.index(item)}]", "The interface input type does not match its target port."))
            elif incoming[(item.target.node, item.target.port)] and port.cardinality == "one":
                issues.append(self._issue("workflow.interface_input_conflict", f"interface.inputs[{workflow.interface.inputs.index(item)}].target", "An input port cannot have both an interface input and an edge."))

        for index, item in enumerate(workflow.interface.outputs):
            source_definition = definitions.get(item.source.node)
            port = next((candidate for candidate in source_definition.output_ports if candidate.name == item.source.port), None) if source_definition else None
            if source_definition is None or port is None:
                issues.append(self._issue("workflow.interface_output_source_missing", f"interface.outputs[{index}].source", "The interface output source port does not exist."))
            elif port.value_type != item.value_type:
                issues.append(self._issue("workflow.interface_output_type_mismatch", f"interface.outputs[{index}]", "The interface output type does not match its source port."))

        if issues:
            return issues

        # Stage 1 compiles a DAG. Loops are a later structural-node contract.
        indegree: dict[str, int] = {node_id: 0 for node_id in nodes}
        for source, targets in adjacency.items():
            for target in targets:
                indegree[target] += 1
        queue = deque(node_id for node_id, count in indegree.items() if count == 0)
        visited: list[str] = []
        while queue:
            node_id = queue.popleft()
            visited.append(node_id)
            for target_id in adjacency[node_id]:
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)
        if len(visited) != len(nodes):
            issues.append(self._issue("workflow.cycle_not_yet_supported", "edges", "Graph cycles require an explicit Loop or Iteration node."))

        roots = {item.target.node for item in workflow.interface.inputs}
        reachable: set[str] = set()
        pending = list(roots)
        while pending:
            node_id = pending.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            pending.extend(adjacency[node_id])
        missing = set(nodes) - reachable
        if missing:
            issues.append(self._issue("workflow.node_unreachable", "nodes", "Every node must be reachable from a Graph input."))
        if any(item.source.node not in reachable for item in workflow.interface.outputs):
            issues.append(self._issue("workflow.interface_output_unreachable", "interface.outputs", "Every Graph output must be reachable from an input."))
        return issues

    def _reference_issues(self, workflow: WorkflowDefinition, *, owner_id: str) -> list[ValidationIssue]:
        assert self._workflow_lookup is not None
        issues: list[ValidationIssue] = []
        active: set[str] = {owner_id} if owner_id else set()

        def visit(definition: WorkflowDefinition, depth: int, path: str) -> None:
            for index, node in enumerate(definition.nodes):
                node_definition = self._catalog.get(node.type)
                if node_definition is None or node_definition.execution_kind != "workflow":
                    continue
                child_id = node.config.get("workflow_id")
                node_path = f"{path}nodes[{index}].config.workflow_id"
                if not isinstance(child_id, str) or not child_id:
                    continue
                if child_id in active:
                    issues.append(self._issue("workflow.reference_cycle", node_path, "Workflow references may not form a cycle."))
                    continue
                if depth >= self._max_nested_depth:
                    issues.append(self._issue("workflow.nesting_too_deep", node_path, "Workflow nesting exceeds the configured limit."))
                    continue
                child = self._workflow_lookup(child_id)
                if child is None:
                    issues.append(self._issue("workflow.reference_missing", node_path, "The referenced Workflow does not exist."))
                    continue
                try:
                    child_definition = WorkflowDefinition.model_validate({key: value for key, value in child.items() if key not in {"id", "revision"}})
                except ValidationError:
                    issues.append(self._issue("workflow.reference_invalid", node_path, "The referenced Workflow is invalid."))
                    continue
                active.add(child_id)
                visit(child_definition, depth + 1, f"{node_path}.")
                active.remove(child_id)

        visit(workflow, 1, "")
        return issues
