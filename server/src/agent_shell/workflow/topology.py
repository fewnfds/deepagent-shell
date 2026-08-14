from __future__ import annotations

from agent_shell.validation import ValidationIssue
from agent_shell.workflow.catalog import NodeHandleSpec, NodeTypeSpec, node_type_spec
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1


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


def _handle(
    spec: NodeTypeSpec,
    handle_id: str,
    *,
    output: bool,
) -> NodeHandleSpec | None:
    handles = spec.output_handles if output else spec.input_handles
    return next((item for item in handles if item.id == handle_id), None)


def validate_workflow_topology(
    document: WorkflowGraphDocumentV1,
) -> tuple[ValidationIssue, ...]:
    nodes = document.definition.nodes
    edges = document.definition.edges
    node_by_id = {node.id: node for node in nodes}
    specs: dict[str, NodeTypeSpec] = {}
    for node in nodes:
        spec = node_type_spec(node.type, node.type_version)
        assert spec is not None
        specs[node.id] = spec

    issues: list[ValidationIssue] = []
    connections: set[tuple[str, str, str, str]] = set()
    endpoint_connections: dict[tuple[str, bool, str], list[int]] = {}
    outgoing_edge_types: dict[str, set[str]] = {}

    for index, edge in enumerate(edges):
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
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
        source_handle = (
            _handle(specs[source.id], edge.source_handle, output=True)
            if source is not None
            else None
        )
        target_handle = (
            _handle(specs[target.id], edge.target_handle, output=False)
            if target is not None
            else None
        )
        if source is not None and source_handle is None:
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
        if target is not None and target_handle is None:
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
        if (
            source_handle is not None
            and target_handle is not None
            and source_handle.edge_type != target_handle.edge_type
        ):
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.edge_type_mismatch",
                    "",
                    "The Workflow edge connects incompatible endpoint types.",
                    "validation.issue.workflow.edgeTypeMismatch",
                    message_args={
                        "source_type": source_handle.edge_type,
                        "target_type": target_handle.edge_type,
                    },
                )
            )
        if source_handle is not None:
            endpoint_connections.setdefault(
                (edge.source, True, source_handle.id), []
            ).append(index)
            outgoing_edge_types.setdefault(edge.source, set()).add(
                source_handle.edge_type
            )
        if target_handle is not None:
            endpoint_connections.setdefault(
                (edge.target, False, target_handle.id), []
            ).append(index)
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
        else:
            connections.add(connection)

    for node in nodes:
        spec = specs[node.id]
        for output, handles in (
            (False, spec.input_handles),
            (True, spec.output_handles),
        ):
            for handle in handles:
                if handle.max_connections is None:
                    continue
                indexes = endpoint_connections.get((node.id, output, handle.id), [])
                for index in indexes[handle.max_connections :]:
                    edge = edges[index]
                    issues.append(
                        _edge_issue(
                            edge.id,
                            index,
                            "workflow.endpoint_connection_limit_exceeded",
                            "source_handle" if output else "target_handle",
                            "The Workflow endpoint connection limit was exceeded.",
                            "validation.issue.workflow.endpointConnectionLimitExceeded",
                            message_args={
                                "handle": handle.id,
                                "max_connections": handle.max_connections,
                            },
                        )
                    )

        if len(outgoing_edge_types.get(node.id, set())) > 1:
            index = next(
                edge_index
                for edge_index, edge in enumerate(edges)
                if edge.source == node.id
            )
            edge = edges[index]
            issues.append(
                _edge_issue(
                    edge.id,
                    index,
                    "workflow.node_routing_mixed",
                    "",
                    "A Workflow node cannot mix static and conditional routing.",
                    "validation.issue.workflow.nodeRoutingMixed",
                )
            )

        if spec.runtime_kind == "state_condition":
            for handle in spec.output_handles:
                if not endpoint_connections.get((node.id, True, handle.id)):
                    node_index = next(
                        index for index, candidate in enumerate(nodes)
                        if candidate.id == node.id
                    )
                    issues.append(
                        _issue(
                            "workflow.condition_route_missing",
                            f"definition.nodes[{node_index}]",
                            "Every Condition route must connect to a target.",
                            "validation.issue.workflow.conditionRouteMissing",
                            owner_id=node.id,
                            owner_type=node.type,
                            message_args={"handle": handle.id},
                        )
                    )

    node_indexes = {node.id: index for index, node in enumerate(nodes)}
    start_ids = {node.id for node in nodes if node.type == "start"}
    end_ids = {node.id for node in nodes if node.type == "end"}
    agent_ids = {node.id for node in nodes if node.type == "agent"}
    for node_type, ids in (
        ("start", start_ids),
        ("end", end_ids),
        ("agent", agent_ids),
    ):
        if not ids:
            issues.append(
                _issue(
                    f"workflow.{node_type}_required",
                    "definition.nodes",
                    f"The Workflow requires at least one {node_type.title()} node.",
                    f"validation.issue.workflow.{node_type}Required",
                    owner_type="graph",
                )
            )

    if start_ids and end_ids:
        outgoing: dict[str, set[str]] = {node.id: set() for node in nodes}
        incoming: dict[str, set[str]] = {node.id: set() for node in nodes}
        for edge in edges:
            if edge.source in node_by_id and edge.target in node_by_id:
                outgoing[edge.source].add(edge.target)
                incoming[edge.target].add(edge.source)

        reachable_from_start = set(start_ids)
        pending = list(start_ids)
        while pending:
            for target in outgoing[pending.pop()]:
                if target not in reachable_from_start:
                    reachable_from_start.add(target)
                    pending.append(target)

        can_reach_end = set(end_ids)
        pending = list(end_ids)
        while pending:
            for source in incoming[pending.pop()]:
                if source not in can_reach_end:
                    can_reach_end.add(source)
                    pending.append(source)

        for node in nodes:
            index = node_indexes[node.id]
            if node.id not in reachable_from_start:
                issues.append(
                    _issue(
                        "workflow.node_unreachable_from_start",
                        f"definition.nodes[{index}]",
                        "The Workflow node is not reachable from a Start node.",
                        "validation.issue.workflow.nodeUnreachableFromStart",
                        owner_id=node.id,
                        owner_type=node.type,
                    )
                )
            if node.id not in can_reach_end:
                issues.append(
                    _issue(
                        "workflow.node_cannot_reach_end",
                        f"definition.nodes[{index}]",
                        "The Workflow node cannot reach an End node.",
                        "validation.issue.workflow.nodeCannotReachEnd",
                        owner_id=node.id,
                        owner_type=node.type,
                    )
                )

    return tuple(issues)


__all__ = ["validate_workflow_topology"]
