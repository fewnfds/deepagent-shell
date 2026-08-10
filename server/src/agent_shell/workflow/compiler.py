from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.state import AgentShellState
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1
from agent_shell.workflow.topology import validate_workflow_topology
from agent_shell.workflow.validation import admit_workflow_document


def _compile_error(code: str, message: str) -> AgentRuntimeError:
    return AgentRuntimeError(code, message, status_code=422)


def compile_workflow(
    document: WorkflowGraphDocumentV1,
    *,
    agent_graphs: Mapping[str, Any],
) -> Any:
    """Compile the first supported canvas shape into an official StateGraph."""

    admission, normalized = admit_workflow_document(document)
    if normalized is None:
        issue = admission.issues[0]
        raise _compile_error(issue.code, issue.message)

    topology_issues = validate_workflow_topology(normalized)
    if topology_issues:
        issue = topology_issues[0]
        raise _compile_error(issue.code, issue.message)

    nodes = normalized.definition.nodes
    start_nodes = [node for node in nodes if node.type == "start"]
    agent_nodes = [node for node in nodes if node.type == "agent"]
    end_nodes = [node for node in nodes if node.type == "end"]
    if len(agent_nodes) != 1:
        raise _compile_error(
            "workflow.agent_count_unsupported",
            "The first Workflow runtime requires exactly one Agent node.",
        )

    start_node = start_nodes[0]
    agent_node = agent_nodes[0]
    end_node = end_nodes[0]
    agent_graph = agent_graphs.get(agent_node.id)
    if agent_graph is None:
        raise _compile_error(
            "workflow.agent_graph_missing",
            "The Workflow Agent node could not be materialized.",
        )

    builder = StateGraph(AgentShellState)
    builder.add_node(agent_node.id, agent_graph)
    for edge in normalized.definition.edges:
        source = START if edge.source == start_node.id else edge.source
        target = END if edge.target == end_node.id else edge.target
        builder.add_edge(source, target)
    return builder.compile()


__all__ = ["compile_workflow"]
