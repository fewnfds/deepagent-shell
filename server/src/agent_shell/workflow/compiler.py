from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import WorkflowState
from agent_shell.workflow.catalog import node_type_spec
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1
from agent_shell.workflow.topology import validate_workflow_topology
from agent_shell.workflow.validation import admit_workflow_document


def _compile_error(code: str, message: str) -> AgentRuntimeError:
    return AgentRuntimeError(code, message, status_code=422)


def _mapping_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    include_deletions: bool,
) -> dict[str, Any]:
    delta = {
        key: value
        for key, value in after.items()
        if key not in before or before[key] != value
    }
    if include_deletions:
        delta.update({key: None for key in before.keys() - after.keys()})
    return delta


def _invocation_metadata(runtime: Runtime[Any]) -> tuple[str, float]:
    execution_info = runtime.execution_info
    if (
        execution_info is None
        or not execution_info.task_id
        or execution_info.node_first_attempt_time is None
    ):
        raise AgentRuntimeError(
            "workflow.invocation_identity_unavailable",
            "The Workflow runtime did not provide the Agent invocation identity.",
            status_code=500,
        )
    return execution_info.task_id, execution_info.node_first_attempt_time


def _make_agent_node(*, node_id: str, built_agent: Any):
    async def call_agent(
        state: WorkflowState,
        config: RunnableConfig,
        runtime: Runtime[WorkflowRuntimeContext],
    ) -> dict[str, Any]:
        invocation_id, invoked_at = _invocation_metadata(runtime)
        workflow_id = str(runtime.context.workflow.get("id", ""))
        if not workflow_id:
            raise AgentRuntimeError(
                "workflow.identity_unavailable",
                "The Workflow runtime did not provide the Workflow identity.",
                status_code=500,
            )
        parent_shared_vars = dict(state.get("shared_vars", {}))
        parent_files = dict(state.get("files", {}))
        child_input = {
            **dict(built_agent.input_state),
            "messages": [],
            "shared_vars": parent_shared_vars,
            "files": parent_files,
        }
        child_context = runtime.context.for_workflow_agent(
            state,
            workflow_node_id=node_id,
            agent_id=built_agent.agent_id,
            invocation_id=invocation_id,
        )
        result = await built_agent.graph.ainvoke(
            child_input,
            config,
            context=child_context,
        )
        invocation_record = {
            "invocation_id": invocation_id,
            "workflow_id": workflow_id,
            "workflow_node_id": node_id,
            "agent_id": built_agent.agent_id,
            "invoked_at": invoked_at,
            "messages": result["messages"],
        }
        update: dict[str, Any] = {
            "agent_invocations": {invocation_id: invocation_record}
        }
        shared_vars = _mapping_delta(
            parent_shared_vars,
            result.get("shared_vars", {}),
            include_deletions=False,
        )
        if shared_vars:
            update["shared_vars"] = shared_vars
        child_files = result.get("files", parent_files)
        files = _mapping_delta(
            parent_files,
            child_files,
            include_deletions=True,
        )
        if files:
            update["files"] = files
        return update

    return call_agent


def _condition_node(_state: WorkflowState) -> dict[str, Any]:
    return {}


def _json_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(
            left,
            sort_keys=True,
            separators=(",", ":"),
        ) == json.dumps(
            right,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return False


_MISSING = object()


def _context_value(context: WorkflowRuntimeContext) -> dict[str, Any]:
    return {
        "request_id": context.request_id,
        "messages": context.messages,
        "messages_sha": context.messages_sha,
        "workflow": context.workflow,
        "prepare": context.prepare,
        "workflow_state": context.workflow_state,
        "workflow_node_id": context.workflow_node_id,
        "agent_id": context.agent_id,
        "invocation_id": context.invocation_id,
    }


def _json_pointer(root: Any, path: str) -> Any:
    current = root
    if not path:
        return current
    for encoded in path.split("/")[1:]:
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                return _MISSING
            current = current[token]
        elif (
            isinstance(current, Sequence)
            and not isinstance(current, (str, bytes, bytearray))
            and token.isdigit()
            and (token == "0" or not token.startswith("0"))
        ):
            index = int(token)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _make_condition_route(config: Mapping[str, Any]):
    source = str(config["source"])
    path = str(config["path"])
    operator = str(config["operator"])
    expected = config.get("value")

    def route(
        state: WorkflowState,
        runtime: Runtime[WorkflowRuntimeContext],
    ) -> str:
        root = state if source == "state" else _context_value(runtime.context)
        actual = _json_pointer(root, path)
        present = actual is not _MISSING
        if operator == "exists":
            matched = present
        elif operator == "not_exists":
            matched = not present
        elif operator == "not_equals":
            matched = not present or not _json_equal(actual, expected)
        else:
            matched = present and _json_equal(actual, expected)
        return "match" if matched else "otherwise"

    return route


def compile_workflow(
    document: WorkflowGraphDocumentV1,
    *,
    node_agents: Mapping[str, Any],
    checkpointer: Any | None = None,
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

    builder = StateGraph(WorkflowState, context_schema=WorkflowRuntimeContext)
    for node in executable_nodes:
        spec = node_type_spec(node.type, node.type_version)
        assert spec is not None
        if spec.runtime_kind == "state_condition":
            builder.add_node(node.id, _condition_node)
            continue
        built_agent = node_agents.get(node.id)
        if built_agent is None:
            raise _compile_error(
                "workflow.node_graph_missing",
                "The Workflow node could not be materialized.",
            )
        builder.add_node(
            node.id,
            _make_agent_node(node_id=node.id, built_agent=built_agent),
            defer=bool(node.config.get("defer", False)),
        )

    edge_types: dict[str, str] = {}
    for edge in normalized.definition.edges:
        source_node = next(node for node in nodes if node.id == edge.source)
        source_spec = node_type_spec(source_node.type, source_node.type_version)
        assert source_spec is not None
        source_handle = next(
            handle
            for handle in source_spec.output_handles
            if handle.id == edge.source_handle
        )
        edge_types[edge.id] = source_handle.edge_type

    # Group normal incoming edges so LangGraph receives one explicit all-of
    # waiting edge per target instead of several independent triggers.
    incoming: dict[str, list[str]] = {}
    for edge in normalized.definition.edges:
        if edge_types[edge.id] != "normal":
            continue
        source = START if edge.source in entry_ids else edge.source
        target = END if edge.target in exit_ids else edge.target
        sources = incoming.setdefault(target, [])
        if source not in sources:
            sources.append(source)
    for target, sources in incoming.items():
        # START is a virtual sentinel and cannot participate in a list-source
        # waiting edge. Keep entry activation explicit, then group real nodes.
        if START in sources:
            builder.add_edge(START, target)
            sources = [source for source in sources if source != START]
        if not sources:
            continue
        builder.add_edge(sources[0] if len(sources) == 1 else sources, target)

    conditional_edges: dict[str, dict[str, str]] = {}
    for edge in normalized.definition.edges:
        if edge_types[edge.id] != "conditional":
            continue
        target = END if edge.target in exit_ids else edge.target
        conditional_edges.setdefault(edge.source, {})[edge.source_handle] = target
    node_by_id = {node.id: node for node in nodes}
    for source, path_map in conditional_edges.items():
        source_node = node_by_id[source]
        source_spec = node_type_spec(source_node.type, source_node.type_version)
        assert source_spec is not None
        if source_spec.runtime_kind != "state_condition":
            raise _compile_error(
                "workflow.conditional_source_unsupported",
                "The Workflow conditional source is not supported.",
            )
        builder.add_conditional_edges(
            source,
            _make_condition_route(source_node.config),
            path_map,
        )
    return builder.compile(checkpointer=checkpointer)


__all__ = ["compile_workflow"]
