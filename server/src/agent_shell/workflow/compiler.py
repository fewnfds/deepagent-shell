from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from agent_shell.condition_router import (
    ConditionRouterBlock,
    ConditionRouterError,
    run_condition_router,
)
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


def _make_condition_router_node(
    *,
    configuration: ConditionRouterBlock,
    route_targets: Mapping[str, str],
):
    async def call_router(
        state: WorkflowState,
        runtime: Runtime[WorkflowRuntimeContext],
    ) -> Command:
        try:
            result = await run_condition_router(
                configuration.model_dump(mode="python"),
                state=state,
                context=runtime.context,
                allowed_branches=route_targets,
            )
        except ConditionRouterError as exc:
            raise AgentRuntimeError(
                "workflow.condition_router_failed",
                "The Condition Router script failed.",
                status_code=422,
            ) from exc
        targets = list(
            dict.fromkeys(route_targets[branch] for branch in result.activate)
        )
        return Command(update=result.update, goto=targets)

    return call_router


def compile_workflow(
    document: WorkflowGraphDocumentV1,
    *,
    node_agents: Mapping[str, Any],
    condition_routers: Mapping[str, ConditionRouterBlock] | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Compile catalog-declared canvas nodes into an official StateGraph."""

    admission, normalized = admit_workflow_document(document)
    if normalized is None:
        issue = admission.issues[0]
        raise _compile_error(issue.code, issue.message)

    router_configs = condition_routers or {}
    topology_issues = validate_workflow_topology(
        normalized,
        condition_routers=router_configs,
    )
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

    node_by_id = {node.id: node for node in nodes}
    edge_types: dict[str, str] = {}
    branch_targets: dict[str, dict[str, str]] = {}
    for edge in normalized.definition.edges:
        source_node = node_by_id[edge.source]
        source_spec = node_type_spec(source_node.type, source_node.type_version)
        assert source_spec is not None
        source_handle = next(
            handle
            for handle in source_spec.output_handles
            if handle.id == edge.source_handle
        )
        edge_types[edge.id] = source_handle.edge_type
        if source_handle.edge_type == "branch":
            assert edge.branch_key is not None
            branch_targets.setdefault(edge.source, {})[edge.branch_key] = (
                END if edge.target in exit_ids else edge.target
            )

    builder = StateGraph(WorkflowState, context_schema=WorkflowRuntimeContext)
    for node in executable_nodes:
        spec = node_type_spec(node.type, node.type_version)
        assert spec is not None
        if spec.runtime_kind == "command_router":
            configuration = router_configs.get(node.id)
            if configuration is None:
                raise _compile_error(
                    "workflow.condition_router_not_found",
                    "The selected Condition Router configuration does not exist.",
                )
            targets = branch_targets.get(node.id, {})
            builder.add_node(
                node.id,
                _make_condition_router_node(
                    configuration=configuration,
                    route_targets=targets,
                ),
                destinations=tuple(dict.fromkeys(targets.values())),
            )
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
    return builder.compile(checkpointer=checkpointer)


__all__ = ["compile_workflow"]
