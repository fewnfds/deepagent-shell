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

    return tuple(issues)


__all__ = ["validate_workflow_topology"]
