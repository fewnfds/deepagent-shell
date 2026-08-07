from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, RemoveMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy, TimeoutPolicy

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.workflow.catalog import BUILTIN_NODE_CATALOG, NodeDefinition
from agent_shell.workflow.context import WorkflowContext
from agent_shell.workflow.contracts import WorkflowDefinition, WorkflowNode
from agent_shell.workflow.state import WorkflowState, read_path, write_path
from agent_shell.workflow.plugin_context import WorkflowNodeContext
from agent_shell.workflow.validator import WorkflowValidator


AgentInvoker = Callable[[str, list[Any], WorkflowContext], Awaitable[str]]
ToolInvoker = Callable[[str, dict[str, Any], Mapping[str, Any], WorkflowContext], Awaitable[Any]]
PluginInvoker = Callable[[WorkflowNode, NodeDefinition, Mapping[str, Any], WorkflowState, WorkflowContext], Awaitable[Any]]
WorkflowLookup = Callable[[str], dict[str, Any] | None]
NodeEventSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class AgentNodeRuntime:
    graph: Any
    input_state: Mapping[str, Any]
    context: Mapping[str, Any]
    start: Callable[[], Awaitable[None]]
    finish: Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    id: str
    name: str
    definition: WorkflowDefinition
    graph: Any
    cleanup: Callable[[], None] | None = None
    agent_contexts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    start: Callable[[], Awaitable[None]] | None = None
    finish: Callable[[Mapping[str, Any]], Awaitable[None]] | None = None


class WorkflowCompiler:
    """Translate Graph Definition to the official LangGraph StateGraph API."""

    def __init__(
        self,
        *,
        workflow_lookup: WorkflowLookup,
        agent_lookup: Callable[[str], dict[str, Any] | None] | None = None,
        agent_invoker: AgentInvoker,
        tool_invoker: ToolInvoker,
        node_catalog: Mapping[str, NodeDefinition] | None = None,
        event_sink: NodeEventSink | None = None,
        checkpointer: Any = None,
        agent_nodes: Mapping[tuple[str, str], AgentNodeRuntime] | None = None,
        plugin_invoker: PluginInvoker | None = None,
    ) -> None:
        self._lookup = workflow_lookup
        self._agent_lookup = agent_lookup
        self._agent_invoker = agent_invoker
        self._tool_invoker = tool_invoker
        self._catalog = dict(node_catalog or BUILTIN_NODE_CATALOG)
        self._event_sink = event_sink
        self._checkpointer = checkpointer
        self._agent_nodes = dict(agent_nodes or {})
        self._plugin_invoker = plugin_invoker

    def compile(self, record: dict[str, Any]) -> CompiledWorkflow:
        graph_id = str(record.get("id") or "")
        payload = {key: value for key, value in record.items() if key not in {"id", "revision"}}
        report, definition = WorkflowValidator(
            workflow_lookup=self._lookup,
            agent_lookup=self._agent_lookup,
            node_catalog=self._catalog,
        ).validate_payload(payload, stage="workflow_compile", owner_id=graph_id)
        if not report.valid or definition is None:
            raise AgentRuntimeError(
                "workflow_validation_failed",
                report.issues[0].message if report.issues else "The Graph is invalid.",
                status_code=422,
                validation_report=report,
            )
        return self._compile_definition(graph_id, definition, active=(graph_id,))

    def _compile_definition(self, graph_id: str, definition: WorkflowDefinition, *, active: tuple[str, ...]) -> CompiledWorkflow:
        children: dict[str, CompiledWorkflow] = {}
        for node in definition.nodes:
            kind = self._catalog[node.type].execution_kind
            if kind != "workflow":
                continue
            child_id = str(node.config["graph_id"])
            if child_id in active:
                raise AgentRuntimeError("workflow_reference_cycle", "Graph references may not form a cycle.", status_code=422)
            child_record = self._lookup(child_id)
            if child_record is None:
                raise AgentRuntimeError("workflow_reference_missing", "A referenced Graph does not exist.", status_code=409)
            child_payload = {key: value for key, value in child_record.items() if key not in {"id", "revision"}}
            child_definition = WorkflowDefinition.model_validate(child_payload)
            children[node.id] = self._compile_definition(child_id, child_definition, active=(*active, child_id))

        node_by_id = {node.id: node for node in definition.nodes}
        node_definitions = {node.id: self._catalog[node.type] for node in definition.nodes}
        data_bindings: dict[str, dict[str, tuple[str, str]]] = {node.id: {} for node in definition.nodes}
        control_out: dict[str, list[Any]] = {node.id: [] for node in definition.nodes}
        control_in: dict[str, int] = {node.id: 0 for node in definition.nodes}
        for edge in definition.edges:
            if edge.kind == "data":
                data_bindings[edge.target.node][edge.target.port] = (edge.source.node, edge.source.port)
            else:
                control_out[edge.source.node].append(edge)
                control_in[edge.target.node] += 1
        for item in definition.interface.inputs:
            data_bindings[item.target.node][item.target.port] = ("__input__", item.name)

        builder = StateGraph(WorkflowState, context_schema=WorkflowContext)
        roots = list(definition.entry_nodes)
        join_nodes = {
            node_id for node_id, item in node_definitions.items() if item.execution_kind == "join"
        }
        for node in definition.nodes:
            node_definition = node_definitions[node.id]
            retry = None
            attempts = node.max_attempts or node.config.get("max_attempts")
            if isinstance(attempts, int) and attempts > 1:
                retry = RetryPolicy(max_attempts=attempts)
            timeout = node.timeout_seconds or node.config.get("timeout_seconds")
            timeout_policy = TimeoutPolicy(run_timeout=float(timeout)) if isinstance(timeout, (int, float)) and timeout > 0 else None
            runnable = self._node_callable(node, node_definition, data_bindings[node.id], children)
            if node_definition.execution_kind == "agent":
                agent_runtime = self._agent_nodes.get((graph_id, node.id))
                if agent_runtime is not None:
                    runnable = self._agent_subgraph(node, agent_runtime)
            destinations = None
            if node_definition.control_mode == "command":
                destinations = tuple(edge.target.node for edge in control_out[node.id])
            builder.add_node(
                node.id,
                runnable,
                retry_policy=retry,
                timeout=timeout_policy,
                metadata={"graph_node_id": node.id, "node_type": node.type},
                destinations=destinations,
            )

        for node_id, declared_edges in control_out.items():
            if node_definitions[node_id].control_mode == "command":
                continue
            edges = [edge for edge in declared_edges if edge.target.node not in join_nodes]
            if not edges and declared_edges:
                continue
            if not edges:
                builder.add_edge(node_id, END)
                continue
            destinations = {edge.target.node for edge in edges}
            if len(destinations) == 1 and all(edge.condition is None for edge in edges):
                builder.add_edge(node_id, next(iter(destinations)))
                continue

            def route(state: WorkflowState, *, _edges=tuple(edges), _node_id=node_id) -> list[str]:
                status = str((state.get("control") or {}).get(f"node:{_node_id}:status", "success"))
                selected = [edge.target.node for edge in _edges if edge.condition in {None, status}]
                return selected or [edge.target.node for edge in _edges if edge.condition is None]

            builder.add_conditional_edges(node_id, route)

        for join_id in join_nodes:
            sources = [
                edge.source.node
                for edge in definition.edges
                if edge.kind == "control" and edge.target.node == join_id
            ]
            builder.add_edge(sources, join_id)

        async def graph_input(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
            incoming = dict(state.get("inputs") or {})
            ports = dict(state.get("ports") or {})
            for item in definition.interface.inputs:
                if item.name in incoming:
                    ports[f"__input__.{item.name}"] = incoming[item.name]
            return {"ports": ports}

        builder.add_node("__graph_input__", graph_input)
        builder.add_edge(START, "__graph_input__")
        if len(roots) == 1:
            builder.add_edge("__graph_input__", roots[0])
        elif len(roots) > 1:
            builder.add_conditional_edges("__graph_input__", lambda _state: roots)
        else:
            builder.add_edge("__graph_input__", END)
        compiled = builder.compile(checkpointer=self._checkpointer, name=definition.name)
        runtimes = [
            value
            for (owner_graph_id, _node_id), value in self._agent_nodes.items()
            if owner_graph_id == graph_id
        ]

        async def start_agents() -> None:
            for value in runtimes:
                await value.start()

        async def finish_agents(terminal: Mapping[str, Any]) -> None:
            for value in reversed(runtimes):
                await value.finish(terminal)

        return CompiledWorkflow(
            id=graph_id,
            name=definition.name,
            definition=definition,
            graph=compiled,
            agent_contexts={node_id: value.context for (owner_graph_id, node_id), value in self._agent_nodes.items() if owner_graph_id == graph_id},
            start=start_agents if runtimes else None,
            finish=finish_agents if runtimes else None,
        )

    def _agent_subgraph(self, node: WorkflowNode, binding: AgentNodeRuntime) -> Any:
        builder = StateGraph(WorkflowState, context_schema=WorkflowContext)

        async def enter(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
            context = getattr(runtime, "context", None)
            if isinstance(context, WorkflowContext) and context.control is not None:
                await context.control.check(node.id)
            self._emit({"event": "node_started", "node_id": node.id, "node_type": node.type})
            prepared = list(state.get("messages") or binding.input_state.get("messages") or [])
            update: dict[str, Any] = {
                "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *prepared],
                "shared": dict(state.get("shared") or {}),
                "control": dict(state.get("control") or {}),
                "artifacts": dict(state.get("artifacts") or {}),
            }
            files = state.get("files")
            if not isinstance(files, dict):
                files = binding.input_state.get("files")
            if isinstance(files, dict):
                update["files"] = dict(files)
            return update

        async def leave(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
            messages = list(state.get("messages") or [])
            response = ""
            if messages:
                content = getattr(messages[-1], "content", "")
                response = content if isinstance(content, str) else str(content)
            control = dict(state.get("control") or {})
            control[f"node:{node.id}:status"] = "success"
            self._emit({"event": "node_completed", "node_id": node.id, "node_type": node.type, "status": "success"})
            return {
                "shared": dict(state.get("shared") or {}),
                "control": control,
                "artifacts": dict(state.get("artifacts") or {}),
                "files": dict(state.get("files") or {}),
                "ports": {
                    f"{node.id}.response": response,
                    f"{node.id}.messages": messages,
                    f"{node.id}.status": "success",
                },
            }

        builder.add_node("__enter__", enter)
        builder.add_node("agent", binding.graph)
        builder.add_node("__leave__", leave)
        builder.add_edge(START, "__enter__")
        builder.add_edge("__enter__", "agent")
        builder.add_edge("agent", "__leave__")
        builder.add_edge("__leave__", END)
        return builder.compile(name=f"{node.id}-profile")

    def _node_callable(
        self,
        node: WorkflowNode,
        node_definition: NodeDefinition,
        bindings: Mapping[str, tuple[str, str]],
        children: Mapping[str, CompiledWorkflow],
    ) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def run_node(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
            context = getattr(runtime, "context", None)
            if not isinstance(context, WorkflowContext):
                context = WorkflowContext(request_id="", workflow_id="", invocation_id="")
            if context.control is not None:
                await context.control.check(node.id)
            self._emit({"event": "node_started", "node_id": node.id, "node_type": node.type})
            inputs: dict[str, Any] = {}
            update: dict[str, Any] = {}
            ports = state.get("ports") or {}
            for port in node_definition.input_ports:
                binding = bindings.get(port.name)
                if binding is None:
                    if port.name == "messages":
                        inputs[port.name] = list(state.get("messages") or [])
                    elif port.required:
                        raise AgentRuntimeError("workflow.input_missing", f"Node '{node.id}' is missing input '{port.name}'.", status_code=422)
                    continue
                source, source_port = binding
                address = f"{source}.{source_port}"
                if address not in ports:
                    if port.required:
                        raise AgentRuntimeError("workflow.input_unavailable", f"Node '{node.id}' input '{port.name}' is unavailable.", status_code=502)
                    continue
                inputs[port.name] = ports[address]

            kind = node_definition.execution_kind
            if kind == "value":
                outputs = {"value": node.config.get("value")}
            elif kind == "pass":
                outputs = {"value": inputs.get("value")}
            elif kind == "state_update":
                shared = write_path(dict(state.get("shared") or {}), str(node.config["path"]), inputs.get("value", node.config.get("value")), str(node.config.get("operation", "set")))
                outputs = {"status": "success"}
                update = {"shared": shared}
            elif kind == "router":
                value = read_path(dict(state.get("shared") or {}), str(node.config["path"]))
                key = str(value).lower() if isinstance(value, bool) else str(value)
                signal = str(dict(node.config.get("cases") or {}).get(key, node.config["default"]))
                outputs = {"status": signal}
            elif kind == "join":
                outputs = {"status": "success"}
            elif kind == "agent":
                response = await self._agent_invoker(str(node.config["profile_id"]), list(inputs.get("messages") or []), context)
                outputs = {"response": response, "messages": [AIMessage(content=response, name=node.id)], "status": "success"}
            elif kind == "tool":
                arguments = inputs.get("arguments", node.config.get("arguments") or {})
                if not isinstance(arguments, dict):
                    raise AgentRuntimeError("workflow.tool_arguments_invalid", "Tool arguments must be a JSON object.", status_code=422)
                result = await self._tool_invoker(str(node.config["tool_name"]), dict(arguments), inputs, context)
                outputs = {"result": result, "status": "success"}
            elif kind == "workflow":
                child = children[node.id]
                child_input = {"inputs": {"input": inputs.get("input")}, "shared": dict(state.get("shared") or {}), "messages": list(state.get("messages") or [])}
                child_output = await child.graph.ainvoke(child_input, context=context)
                outputs = {"output": dict(child_output.get("output") or child_output.get("shared") or {}), "status": "success"}
            elif kind == "plugin":
                if self._plugin_invoker is None:
                    raise AgentRuntimeError("workflow.plugin_unavailable", "The Workflow node plugin is unavailable.", status_code=422)
                result = await self._plugin_invoker(node, node_definition, inputs, state, context)
                if isinstance(result, Command):
                    self._emit({"event": "node_completed", "node_id": node.id, "node_type": node.type, "status": "command"})
                    return result
                if not isinstance(result, Mapping):
                    raise AgentRuntimeError("workflow.plugin_result_invalid", "A Workflow node plugin must return a State update or Command.", status_code=502)
                outputs = dict(result.get("outputs") or {})
                update = {key: value for key, value in result.items() if key in {"inputs", "shared", "control", "artifacts", "messages", "ports", "output"}}
                outputs["status"] = str(result.get("status", "success"))
            else:
                raise AgentRuntimeError("workflow_node_type_unavailable", "The Workflow node type is unavailable.", status_code=422)
            port_update = dict(update.get("ports", {}))
            for name, value in outputs.items():
                port_update[f"{node.id}.{name}"] = value
            update["ports"] = port_update
            if "messages" in outputs:
                update["messages"] = outputs["messages"]
            control = dict(state.get("control") or {})
            control[f"node:{node.id}:status"] = str(outputs.get("status", "success"))
            update["control"] = control
            self._emit({"event": "node_completed", "node_id": node.id, "node_type": node.type, "status": outputs.get("status", "success")})
            return update

        async def guarded_node(state: WorkflowState, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
            try:
                return await run_node(state, runtime)
            except BaseException:
                self._emit({"event": "node_failed", "node_id": node.id, "node_type": node.type, "status": "failed"})
                raise

        return guarded_node

    def _emit(self, event: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event)
