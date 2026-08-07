from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.workflow.context import WorkflowContext
from agent_shell.workflow.contracts import WorkflowDefinition
from agent_shell.workflow.state import WorkflowState
from agent_shell.workflow.validator import WorkflowValidator


AgentInvoker = Callable[[str, list[Any], WorkflowContext], Awaitable[str]]
ToolInvoker = Callable[[str, dict[str, Any], WorkflowState, WorkflowContext], Awaitable[Any]]
WorkflowLookup = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    id: str
    public_id: str
    name: str
    graph: Any


class WorkflowCompiler:
    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup,
        agent_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        agent_invoker: AgentInvoker,
        tool_invoker: ToolInvoker,
    ) -> None:
        self._lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._agent_invoker = agent_invoker
        self._tool_invoker = tool_invoker

    def compile(self, record: dict[str, Any]) -> CompiledWorkflow:
        return self._compile(record, active=(), depth=1)

    def _compile(
        self,
        record: dict[str, Any],
        *,
        active: tuple[str, ...],
        depth: int,
    ) -> CompiledWorkflow:
        workflow_id = str(record.get("id", ""))
        payload = {
            key: value
            for key, value in record.items()
            if key not in {"id", "revision"}
        }
        report, definition = WorkflowValidator(
            workflow_lookup=self._lookup,
            agent_lookup=self._agent_lookup,
            max_nested_depth=3,
        ).validate_payload(payload, stage="workflow_compile", owner_id=workflow_id)
        if not report.valid or definition is None:
            raise AgentRuntimeError(
                "workflow_validation_failed",
                report.issues[0].message if report.issues else "The Workflow is invalid.",
                status_code=422,
                validation_report=report,
            )
        if workflow_id in active:
            raise AgentRuntimeError(
                "workflow_reference_cycle",
                "Workflow references may not form a cycle.",
                status_code=422,
            )
        if depth > 3:
            raise AgentRuntimeError(
                "workflow_nesting_too_deep",
                "Workflow nesting may not exceed three levels.",
                status_code=422,
            )

        children: dict[str, CompiledWorkflow] = {}
        for node in definition.nodes:
            if node.type != "builtin.workflow.call":
                continue
            child_id = str(node.config["workflow_id"])
            child_record = self._lookup(child_id)
            if child_record is None:
                raise AgentRuntimeError(
                    "workflow_reference_missing",
                    "A referenced Workflow does not exist.",
                    status_code=409,
                )
            children[node.id] = self._compile(
                child_record,
                active=(*active, workflow_id),
                depth=depth + 1,
            )

        builder = StateGraph(WorkflowState, context_schema=WorkflowContext)
        for node in definition.nodes:
            builder.add_node(
                node.id,
                self._node_callable(
                    node.id,
                    node.type,
                    dict(node.config),
                    children,
                    base_agent_id=(
                        definition.agent_base.source.id
                        if definition.agent_base is not None
                        else None
                    ),
                ),
            )

        input_node = next(
            node for node in definition.nodes if node.type == "builtin.input.messages"
        )
        output_node = next(
            node for node in definition.nodes if node.type == "builtin.output.message"
        )
        builder.add_edge(START, input_node.id)
        for edge in definition.edges:
            builder.add_edge(edge.source.node, edge.target.node)
        builder.add_edge(output_node.id, END)
        try:
            graph = builder.compile()
        except Exception as exc:
            raise AgentRuntimeError(
                "workflow_compile_failed",
                "The Workflow graph could not be compiled.",
                status_code=422,
            ) from exc
        return CompiledWorkflow(
            id=workflow_id,
            public_id=definition.public_id,
            name=definition.name,
            graph=graph,
        )

    def _node_callable(
        self,
        node_id: str,
        node_type: str,
        config: dict[str, Any],
        children: dict[str, CompiledWorkflow],
        base_agent_id: str | None,
    ):
        if node_type in {"builtin.input.messages", "builtin.output.message"}:
            async def boundary_node(
                state: WorkflowState,
                runtime: Any,
            ) -> WorkflowState:
                return {"node_outputs": {node_id: {"messages": state.get("messages", [])}}}

            return boundary_node

        if node_type == "builtin.agent.call":
            async def agent_node(state: WorkflowState, runtime: Any) -> WorkflowState:
                context = runtime.context
                agent_id = str(config.get("agent_id") or base_agent_id or "")
                if not agent_id:
                    raise AgentRuntimeError(
                        "workflow.agent_reference_required",
                        "Agent nodes require an Agent reference or AgentBase.",
                        status_code=422,
                    )
                text = await self._agent_invoker(
                    agent_id,
                    list(state.get("messages", [])),
                    context,
                )
                message = AIMessage(content=text, name=node_id)
                return {
                    "messages": [message],
                    "node_outputs": {node_id: {"message": text}},
                }

            return agent_node

        if node_type == "builtin.tool.call":
            async def tool_node(state: WorkflowState, runtime: Any) -> WorkflowState:
                context = runtime.context
                result = await self._tool_invoker(
                    str(config["tool_name"]),
                    dict(config.get("arguments") or {}),
                    state,
                    context,
                )
                text = result if isinstance(result, str) else str(result)
                return {
                    "messages": [AIMessage(content=text, name=node_id)],
                    "node_outputs": {node_id: {"result": result}},
                }

            return tool_node

        if node_type == "builtin.workflow.call":
            child = children[node_id]

            async def workflow_node(state: WorkflowState, runtime: Any) -> WorkflowState:
                child_output = await child.graph.ainvoke(
                    {
                        "messages": list(state.get("messages", [])),
                        "node_outputs": {},
                    },
                    context=runtime.context,
                )
                messages = list(child_output.get("messages", []))
                return {
                    "messages": messages[-1:] if messages else [],
                    "node_outputs": {
                        node_id: {
                            "workflow_id": child.id,
                            "messages": messages[-1:] if messages else [],
                        }
                    },
                }

            return workflow_node

        raise AgentRuntimeError(
            "workflow_node_type_unavailable",
            "The Workflow contains an unavailable node type.",
            status_code=422,
        )
