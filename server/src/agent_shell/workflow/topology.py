from __future__ import annotations

from collections import deque

from agent_shell.validation import ValidationIssue
from agent_shell.workflow.catalog import NodeTypeSpec, node_type_spec
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1, WorkflowNodeV1


def _issue(
    code: str,
    path: str,
    message: str,
    message_key: str,
    *,
    owner_id: str = "",
    owner_type: str = "",
    message_args: dict[str, str | int] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        scope="workflow",
        owner_id=owner_id,
        owner_name=owner_id,
        owner_type=owner_type,
        path=path,
        message=message,
        message_key=message_key,
        message_args=message_args or {},
    )


def _node_issue(
    node: WorkflowNodeV1,
    index: int,
    code: str,
    message: str,
    message_key: str,
    *,
    message_args: dict[str, str | int] | None = None,
) -> ValidationIssue:
    return _issue(
        code,
        f"definition.nodes[{index}]",
        message,
        message_key,
        owner_id=node.id,
        owner_type=node.type,
        message_args=message_args,
    )


def _edge_issue(
    edge_id: str,
    index: int,
    code: str,
    field: str,
    message: str,
    message_key: str,
    *,
    message_args: dict[str, str | int] | None = None,
) -> ValidationIssue:
    path = f"definition.edges[{index}]"
    if field:
        path += f".{field}"
    return _issue(
        code,
        path,
        message,
        message_key,
        owner_id=edge_id,
        owner_type="edge",
        message_args=message_args,
    )


def _has_handle(spec: NodeTypeSpec, handle_id: str, *, output: bool) -> bool:
    handles = spec.output_handles if output else spec.input_handles
    return any(item.id == handle_id for item in handles)


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    pending = [start]
    while pending:
        node_id = pending.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        pending.extend(adjacency[node_id] - seen)
    return seen


def validate_workflow_topology(
    document: WorkflowGraphDocumentV1,
) -> tuple[ValidationIssue, ...]:
    nodes = document.definition.nodes
    edges = document.definition.edges
    node_by_id = {node.id: node for node in nodes}
    node_index = {node.id: index for index, node in enumerate(nodes)}
    specs: dict[str, NodeTypeSpec] = {}
    for node in nodes:
        spec = node_type_spec(node.type, node.type_version)
        assert spec is not None
        specs[node.id] = spec

    issues: list[ValidationIssue] = []
    by_type = {
        node_type: [node for node in nodes if node.type == node_type]
        for node_type in ("start", "agent", "end")
    }
    for node_type in ("start", "end"):
        count = len(by_type[node_type])
        if count != 1:
            issues.append(
                _issue(
                    f"workflow.{node_type}_count_invalid",
                    "definition.nodes",
                    f"An executable Workflow requires exactly one {node_type.title()} node.",
                    f"validation.issue.workflow.{node_type}CountInvalid",
                    owner_type="graph",
                    message_args={"count": count},
                )
            )
    if not by_type["agent"]:
        issues.append(
            _issue(
                "workflow.agent_required",
                "definition.nodes",
                "An executable Workflow requires at least one Agent node.",
                "validation.issue.workflow.agentRequired",
                owner_type="graph",
            )
        )

    incoming = {node.id: 0 for node in nodes}
    outgoing = {node.id: 0 for node in nodes}
    adjacency = {node.id: set() for node in nodes}
    reverse = {node.id: set() for node in nodes}
    connections: set[tuple[str, str, str, str]] = set()

    for index, edge in enumerate(edges):
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
        valid = True
        if source is None:
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_source_not_found",
                    "source",
                    "The Workflow edge source node does not exist.",
                    "validation.issue.workflow.edgeSourceNotFound",
                    message_args={"node_id": edge.source},
                )
            )
            valid = False
        if target is None:
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_target_not_found",
                    "target",
                    "The Workflow edge target node does not exist.",
                    "validation.issue.workflow.edgeTargetNotFound",
                    message_args={"node_id": edge.target},
                )
            )
            valid = False
        if source is not None and not _has_handle(
            specs[source.id], edge.source_handle, output=True
        ):
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_source_handle_invalid",
                    "source_handle",
                    "The source handle is not available on this Workflow node.",
                    "validation.issue.workflow.edgeSourceHandleInvalid",
                    message_args={"handle": edge.source_handle},
                )
            )
            valid = False
        if target is not None and not _has_handle(
            specs[target.id], edge.target_handle, output=False
        ):
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_target_handle_invalid",
                    "target_handle",
                    "The target handle is not available on this Workflow node.",
                    "validation.issue.workflow.edgeTargetHandleInvalid",
                    message_args={"handle": edge.target_handle},
                )
            )
            valid = False
        connection = (
            edge.source,
            edge.source_handle,
            edge.target,
            edge.target_handle,
        )
        if connection in connections:
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_duplicate",
                    "",
                    "The Workflow contains the same connection more than once.",
                    "validation.issue.workflow.edgeDuplicate",
                )
            )
            valid = False
        else:
            connections.add(connection)
        if not valid:
            continue
        incoming[edge.target] += 1
        outgoing[edge.source] += 1
        adjacency[edge.source].add(edge.target)
        reverse[edge.target].add(edge.source)

    for node in nodes:
        index = node_index[node.id]
        expected_in = 0 if node.type == "start" else 1
        expected_out = 0 if node.type == "end" else 1
        if incoming[node.id] != expected_in:
            issues.append(
                _node_issue(
                    node,
                    index,
                    "workflow.node_input_cardinality_invalid",
                    "The Workflow node has an invalid number of incoming edges.",
                    "validation.issue.workflow.nodeInputCardinalityInvalid",
                    message_args={"expected": expected_in, "actual": incoming[node.id]},
                )
            )
        if outgoing[node.id] != expected_out:
            issues.append(
                _node_issue(
                    node,
                    index,
                    "workflow.node_output_cardinality_invalid",
                    "The Workflow node has an invalid number of outgoing edges.",
                    "validation.issue.workflow.nodeOutputCardinalityInvalid",
                    message_args={"expected": expected_out, "actual": outgoing[node.id]},
                )
            )

    if len(by_type["start"]) == 1:
        reachable = _reachable(by_type["start"][0].id, adjacency)
        for node in nodes:
            if node.id not in reachable:
                issues.append(
                    _node_issue(
                        node,
                        node_index[node.id],
                        "workflow.node_unreachable",
                        "The Workflow node is not reachable from Start.",
                        "validation.issue.workflow.nodeUnreachable",
                    )
                )
    if len(by_type["end"]) == 1:
        reaches_end = _reachable(by_type["end"][0].id, reverse)
        for node in nodes:
            if node.id not in reaches_end:
                issues.append(
                    _node_issue(
                        node,
                        node_index[node.id],
                        "workflow.node_dead_end",
                        "The Workflow node cannot reach End.",
                        "validation.issue.workflow.nodeDeadEnd",
                    )
                )

    remaining_incoming = dict(incoming)
    queue = deque(
        node_id for node_id, degree in remaining_incoming.items() if degree == 0
    )
    visited = 0
    while queue:
        node_id = queue.popleft()
        visited += 1
        for target in adjacency[node_id]:
            remaining_incoming[target] -= 1
            if remaining_incoming[target] == 0:
                queue.append(target)
    if visited != len(nodes):
        issues.append(
            _issue(
                "workflow.graph_cycle",
                "definition.edges",
                "The first Workflow graph version does not allow cycles.",
                "validation.issue.workflow.graphCycle",
                owner_type="graph",
            )
        )

    return tuple(issues)


__all__ = ["validate_workflow_topology"]
