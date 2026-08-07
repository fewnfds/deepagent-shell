from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport
from agent_shell.workflow.catalog import BUILTIN_NODE_CATALOG, NodeDefinition
from agent_shell.workflow.contracts import WorkflowDefinition


WorkflowLookup = Callable[[str], dict[str, Any] | None]
AgentLookup = Callable[[str], dict[str, Any] | None]


class WorkflowValidator:
    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup | None = None,
        agent_lookup: AgentLookup | None = None,
        node_catalog: dict[str, NodeDefinition] | None = None,
        max_nested_depth: int = 3,
    ) -> None:
        self._workflow_lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._catalog = node_catalog or BUILTIN_NODE_CATALOG
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
        if definition.agent_base is not None and self._agent_lookup is not None:
            if self._agent_lookup(definition.agent_base.source.id) is None:
                issues.append(
                    self._issue(
                        "workflow.agent_base_missing",
                        "agent_base.source.id",
                        "The AgentBase Main Agent profile does not exist.",
                    )
                )
        report = ValidationReport(stage=stage, issues=tuple(issues))
        return report, definition if report.valid else None

    def _graph_issues(self, workflow: WorkflowDefinition) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        nodes: dict[str, Any] = {}
        for index, node in enumerate(workflow.nodes):
            if node.id in nodes:
                issues.append(self._issue("workflow.node_id_duplicate", f"nodes[{index}].id", "Workflow node ids must be unique."))
            else:
                nodes[node.id] = node
            definition = self._catalog.get(node.type)
            if definition is None or definition.version != node.version:
                issues.append(self._issue("workflow.node_type_unknown", f"nodes[{index}].type", "The Workflow node type or version is unavailable."))
            elif node.type == "builtin.agent.call":
                agent_id = node.config.get("agent_id")
                if not isinstance(agent_id, str) or not agent_id:
                    if workflow.agent_base is not None:
                        continue
                    issues.append(self._issue("workflow.agent_reference_required", f"nodes[{index}].config.agent_id", "Agent nodes require an Agent reference."))
                elif self._agent_lookup is not None and self._agent_lookup(agent_id) is None:
                    issues.append(self._issue("workflow.agent_reference_missing", f"nodes[{index}].config.agent_id", "The referenced Agent does not exist."))
            elif node.type == "builtin.tool.call" and not isinstance(node.config.get("tool_name"), str):
                issues.append(self._issue("workflow.tool_reference_required", f"nodes[{index}].config.tool_name", "Tool nodes require a tool name."))

        input_nodes = [node for node in workflow.nodes if node.type == "builtin.input.messages"]
        output_nodes = [node for node in workflow.nodes if node.type == "builtin.output.message"]
        if len(input_nodes) != 1:
            issues.append(self._issue("workflow.input_count_invalid", "nodes", "A Workflow must contain exactly one input node."))
        if len(output_nodes) != 1:
            issues.append(self._issue("workflow.output_count_invalid", "nodes", "A Workflow must contain exactly one output node."))

        edge_ids: set[str] = set()
        adjacency: dict[str, set[str]] = defaultdict(set)
        incoming: dict[str, int] = defaultdict(int)
        for index, edge in enumerate(workflow.edges):
            if edge.id in edge_ids:
                issues.append(self._issue("workflow.edge_id_duplicate", f"edges[{index}].id", "Workflow edge ids must be unique."))
            edge_ids.add(edge.id)
            source = nodes.get(edge.source.node)
            target = nodes.get(edge.target.node)
            if source is None:
                issues.append(self._issue("workflow.edge_source_missing", f"edges[{index}].source.node", "The source node does not exist."))
                continue
            if target is None:
                issues.append(self._issue("workflow.edge_target_missing", f"edges[{index}].target.node", "The target node does not exist."))
                continue
            source_definition = self._catalog.get(source.type)
            target_definition = self._catalog.get(target.type)
            if source_definition is None or target_definition is None:
                continue
            source_ports = {port.name: port for port in source_definition.output_ports}
            target_ports = {port.name: port for port in target_definition.input_ports}
            source_port = source_ports.get(edge.source.port)
            target_port = target_ports.get(edge.target.port)
            if source_port is None:
                issues.append(self._issue("workflow.source_port_missing", f"edges[{index}].source.port", "The source output port does not exist."))
                continue
            if target_port is None:
                issues.append(self._issue("workflow.target_port_missing", f"edges[{index}].target.port", "The target input port does not exist."))
                continue
            if source_port.data_type != target_port.data_type:
                issues.append(self._issue("workflow.port_type_mismatch", f"edges[{index}]", "The connected Workflow ports have incompatible types."))
                continue
            if edge.target.node in adjacency[edge.source.node]:
                issues.append(self._issue("workflow.edge_duplicate", f"edges[{index}]", "The same node connection is declared more than once."))
                continue
            adjacency[edge.source.node].add(edge.target.node)
            incoming[edge.target.node] += 1

        if not issues and nodes:
            queue = deque(node_id for node_id in nodes if incoming[node_id] == 0)
            visited: list[str] = []
            while queue:
                node_id = queue.popleft()
                visited.append(node_id)
                for target_id in adjacency[node_id]:
                    incoming[target_id] -= 1
                    if incoming[target_id] == 0:
                        queue.append(target_id)
            if len(visited) != len(nodes):
                issues.append(self._issue("workflow.cycle_forbidden", "edges", "Workflow cycles are not allowed."))
            elif input_nodes and output_nodes:
                reachable: set[str] = set()
                pending = [input_nodes[0].id]
                while pending:
                    node_id = pending.pop()
                    if node_id in reachable:
                        continue
                    reachable.add(node_id)
                    pending.extend(adjacency[node_id])
                missing = set(nodes) - reachable
                if missing:
                    issues.append(self._issue("workflow.node_unreachable", "nodes", "Every Workflow node must be reachable from the input node."))
                if output_nodes[0].id not in reachable:
                    issues.append(self._issue("workflow.output_unreachable", "nodes", "The Workflow output node must be reachable from the input node."))
        return issues

    def _reference_issues(
        self, workflow: WorkflowDefinition, *, owner_id: str
    ) -> list[ValidationIssue]:
        assert self._workflow_lookup is not None
        issues: list[ValidationIssue] = []
        active: set[str] = {owner_id} if owner_id else set()

        def visit(definition: WorkflowDefinition, depth: int, path: str) -> None:
            for index, node in enumerate(definition.nodes):
                if node.type != "builtin.workflow.call":
                    continue
                child_id = node.config.get("workflow_id")
                node_path = f"{path}nodes[{index}].config.workflow_id"
                if not isinstance(child_id, str) or not child_id:
                    issues.append(self._issue("workflow.reference_required", node_path, "workflow.call requires a Workflow reference."))
                    continue
                if child_id in active:
                    issues.append(self._issue("workflow.reference_cycle", node_path, "Workflow references may not form a cycle."))
                    continue
                if depth >= self._max_nested_depth:
                    issues.append(self._issue("workflow.nesting_too_deep", node_path, "Workflow nesting may not exceed three levels."))
                    continue
                child = self._workflow_lookup(child_id)
                if child is None:
                    issues.append(self._issue("workflow.reference_missing", node_path, "The referenced Workflow does not exist."))
                    continue
                try:
                    child_definition = WorkflowDefinition.model_validate(
                        {
                            key: value
                            for key, value in child.items()
                            if key not in {"id", "revision"}
                        }
                    )
                except ValidationError:
                    issues.append(self._issue("workflow.reference_invalid", node_path, "The referenced Workflow is invalid."))
                    continue
                active.add(child_id)
                visit(child_definition, depth + 1, f"{node_path}.")
                active.remove(child_id)

        visit(workflow, 1, "")
        return issues
