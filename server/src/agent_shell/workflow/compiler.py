from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.state import AgentShellState
from agent_shell.workflow.catalog import node_type_spec
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1
from agent_shell.workflow.topology import validate_workflow_topology
from agent_shell.workflow.validation import admit_workflow_document


def _compile_error(code: str, message: str) -> AgentRuntimeError:
    return AgentRuntimeError(code, message, status_code=422)


def compile_workflow(
    document: WorkflowGraphDocumentV1,
    *,
    node_graphs: Mapping[str, Any],
) -> Any:
    """Compile catalog-declared canvas nodes into an official StateGraph."""

    admission, normalized = admit_workflow_document(document)
    if normalized is None:
        issue = admission.issues[0]
        raise _compile_error(issue.code, issue.message)

    topology_issues = validate_workflow_topology(normalized)
    if topology_issues:
        issue = topology_issues[0]
        raise _compile_error(issue.code, issue.message)

    nodes = normalized.definition.nodes
    entry_ids: set[str] = set()
    exit_ids: set[str] = set()
    executable_nodes = []
    for node in nodes:
        spec = node_type_spec(node.type, node.type_version)
        assert spec is not None
        if spec.runtime_kind == "graph_entry":
            entry_ids.add(node.id)
        elif spec.runtime_kind == "graph_exit":
            exit_ids.add(node.id)
        else:
            executable_nodes.append(node)

    builder = StateGraph(AgentShellState)
    for node in executable_nodes:
        node_graph = node_graphs.get(node.id)
        if node_graph is None:
            raise _compile_error(
                "workflow.node_graph_missing",
                "The Workflow node could not be materialized.",
            )
        builder.add_node(node.id, node_graph)
    for edge in normalized.definition.edges:
        source = START if edge.source in entry_ids else edge.source
        target = END if edge.target in exit_ids else edge.target
        builder.add_edge(source, target)
    return builder.compile()


__all__ = ["compile_workflow"]
