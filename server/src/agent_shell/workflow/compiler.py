from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.workflow.catalog import BUILTIN_NODE_CATALOG, NodeDefinition
from agent_shell.workflow.context import WorkflowContext
from agent_shell.workflow.contracts import WorkflowDefinition, WorkflowPortRef
from agent_shell.workflow.state import WorkflowState
from agent_shell.workflow.validator import WorkflowValidator


AgentInvoker = Callable[[str, list[Any], WorkflowContext], Awaitable[str]]
ToolInvoker = Callable[[str, dict[str, Any], Mapping[str, Any], WorkflowContext], Awaitable[Any]]
WorkflowLookup = Callable[[str], dict[str, Any] | None]

GRAPH_INPUT_NODE = "__graph_input__"
GRAPH_OUTPUT_NODE = "__graph_output__"


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    id: str
    name: str
    definition: WorkflowDefinition
    graph: Any


class WorkflowCompiler:
    """Compile a validated GraphDefinition into a LangGraph StateGraph."""

    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup,
        agent_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        agent_invoker: AgentInvoker,
        tool_invoker: ToolInvoker,
        node_catalog: dict[str, NodeDefinition] | None = None,
    ) -> None:
        self._lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._agent_invoker = agent_invoker
        self._tool_invoker = tool_invoker
        self._catalog = node_catalog or BUILTIN_NODE_CATALOG

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
        payload = {key: value for key, value in record.items() if key not in {"id", "revision"}}
        report, definition = WorkflowValidator(
            workflow_lookup=self._lookup,
            agent_lookup=self._agent_lookup,
            node_catalog=self._catalog,
            max_nested_depth=8,
        ).validate_payload(payload, stage="workflow_compile", owner_id=workflow_id)
        if not report.valid or definition is None:
            raise AgentRuntimeError(
                "workflow_validation_failed",
                report.issues[0].message if report.issues else "The Workflow is invalid.",
                status_code=422,
                validation_report=report,
            )
        if workflow_id in active:
            raise AgentRuntimeError("workflow_reference_cycle", "Workflow references may not form a cycle.", status_code=422)
        if depth > 8:
            raise AgentRuntimeError("workflow_nesting_too_deep", "Workflow nesting exceeds the configured limit.", status_code=422)

        children: dict[str, CompiledWorkflow] = {}
        for node in definition.nodes:
            node_definition = self._catalog.get(node.type)
            if node_definition is None or node_definition.execution_kind != "workflow":
                continue
            child_id = str(node.config["workflow_id"])
            child_record = self._lookup(child_id)
            if child_record is None:
                raise AgentRuntimeError("workflow_reference_missing", "A referenced Workflow does not exist.", status_code=409)
            children[node.id] = self._compile(child_record, active=(*active, workflow_id), depth=depth + 1)

        bindings: dict[str, dict[str, str]] = {node.id: {} for node in definition.nodes}
        for item in definition.interface.inputs:
            bindings[item.target.node][item.target.port] = f"{GRAPH_INPUT_NODE}.{item.name}"
        node_edges: set[tuple[str, str]] = set()
        for edge in definition.edges:
            bindings[edge.target.node][edge.target.port] = f"{edge.source.node}.{edge.source.port}"
            node_edges.add((edge.source.node, edge.target.node))

        builder = StateGraph(WorkflowState, context_schema=WorkflowContext)

        async def graph_input(state: WorkflowState, _runtime: Any) -> WorkflowState:
            values = dict(state.get("input_values") or {})
            return {"port_values": {f"{GRAPH_INPUT_NODE}.{name}": value for name, value in values.items()}}

        async def graph_output(state: WorkflowState, _runtime: Any) -> WorkflowState:
            port_values = state.get("port_values") or {}
            output_values: dict[str, Any] = {}
            for item in definition.interface.outputs:
                address = f"{item.source.node}.{item.source.port}"
                if address not in port_values:
                    if item.required:
                        raise AgentRuntimeError("workflow.output_missing", f"Graph output '{item.name}' was not produced.", status_code=502)
                    continue
                output_values[item.name] = port_values[address]
            return {"output_values": output_values}

        builder.add_node(GRAPH_INPUT_NODE, graph_input)
        builder.add_node(GRAPH_OUTPUT_NODE, graph_output)
        builder.add_edge(START, GRAPH_INPUT_NODE)

        for node in definition.nodes:
            builder.add_node(
                node.id,
                self._node_callable(
                    node,
                    self._catalog[node.type],
                    children,
                    bindings[node.id],
                    base_agent_id=definition.agent_base_id,
                ),
            )

        for source, target in node_edges:
            builder.add_edge(source, target)
        for item in definition.interface.inputs:
            builder.add_edge(GRAPH_INPUT_NODE, item.target.node)
        output_sources = sorted({item.source.node for item in definition.interface.outputs})
        builder.add_edge(output_sources if len(output_sources) > 1 else output_sources[0], GRAPH_OUTPUT_NODE)
        builder.add_edge(GRAPH_OUTPUT_NODE, END)
        try:
            graph = builder.compile()
        except Exception as exc:
            raise AgentRuntimeError("workflow_compile_failed", "The Workflow graph could not be compiled.", status_code=422) from exc
        return CompiledWorkflow(id=workflow_id, name=definition.name, definition=definition, graph=graph)

    def _node_callable(
        self,
        node: Any,
        node_definition: NodeDefinition,
        children: dict[str, CompiledWorkflow],
        bindings: Mapping[str, str],
        base_agent_id: str | None,
    ) -> Callable[..., Awaitable[WorkflowState]]:
        async def run_node(state: WorkflowState, runtime: Any) -> WorkflowState:
            port_values = state.get("port_values") or {}
            inputs: dict[str, Any] = {}
            for port in node_definition.input_ports:
                address = bindings.get(port.name)
                if address is None:
                    if port.required:
                        raise AgentRuntimeError("workflow.input_missing", f"Node '{node.id}' is missing input '{port.name}'.", status_code=422)
                    continue
                if address not in port_values:
                    raise AgentRuntimeError("workflow.input_unavailable", f"Node '{node.id}' input '{port.name}' is not available.", status_code=502)
                inputs[port.name] = port_values[address]

            kind = node_definition.execution_kind
            if kind == "value":
                outputs = {"value": node.config["value"]}
            elif kind == "pass":
                outputs = {"value": inputs["value"]}
            elif kind == "agent":
                agent_id = str(node.config.get("agent_id") or base_agent_id or "")
                if not agent_id:
                    raise AgentRuntimeError("workflow.agent_reference_required", "Agent nodes require an Agent profile or graph AgentBase.", status_code=422)
                response = await self._agent_invoker(agent_id, list(inputs["messages"]), runtime.context)
                outputs = {"response": response, "messages": [AIMessage(content=response, name=node.id)]}
            elif kind == "tool":
                arguments = inputs.get("arguments", node.config.get("arguments") or {})
                if not isinstance(arguments, dict):
                    raise AgentRuntimeError("workflow.tool_arguments_invalid", "Tool arguments must be a JSON object.", status_code=422)
                result = await self._tool_invoker(str(node.config["tool_name"]), dict(arguments), inputs, runtime.context)
                outputs = {"result": result}
            elif kind == "workflow":
                child = children[node.id]
                child_output = await child.graph.ainvoke(
                    {"input_values": {"input": inputs["input"]}},
                    context=runtime.context,
                )
                outputs = {"output": dict(child_output.get("output_values") or {})}
            else:
                raise AgentRuntimeError("workflow_node_type_unavailable", "The Workflow contains an unavailable node type.", status_code=422)

            declared = {port.name for port in node_definition.output_ports}
            unexpected = set(outputs) - declared
            if unexpected:
                raise AgentRuntimeError("workflow.node_output_invalid", f"Node '{node.id}' returned undeclared outputs.", status_code=502)
            return {"port_values": {f"{node.id}.{name}": value for name, value in outputs.items()}}

        return run_node
