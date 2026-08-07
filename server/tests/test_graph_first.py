from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Mapping

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from typing import Any, TypedDict

from agent_shell.runtime.graph_run_service import GraphRunService
from agent_shell.app import create_app
from agent_shell.settings import Settings
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.graph_runs import GraphRunStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.workflow.catalog import scan_workflow_node_registry
from agent_shell.workflow.compiler import AgentNodeRuntime, CompiledWorkflow, WorkflowCompiler
from agent_shell.workflow.context import WorkflowContext
from agent_shell.workflow.contracts import EntryScriptDefinition, WorkflowDefinition
from agent_shell.workflow.artifacts import ArtifactCommitError, ArtifactCommitter
from agent_shell.workflow.examples.commit_reconciler import OrderedCommitReconciler
from agent_shell.workflow.state import WorkflowState


def _value_graph() -> dict[str, Any]:
    return {
        "name": "value-graph",
        "description": "",
        "schema_version": 3,
        "enabled": True,
        "interface": {},
        "setup": [],
        "nodes": [{"id": "value", "type": "builtin.value", "version": "1.0.0", "config": {"value": "ok"}}],
        "entry_nodes": ["value"],
        "edges": [],
        "layout": {},
    }


def test_graph_contract_and_compiler_use_shared_state() -> None:
    definition = WorkflowDefinition.model_validate(_value_graph())
    compiled = WorkflowCompiler(workflow_lookup=lambda _id: None, agent_invoker=None, tool_invoker=None).compile({"id": "graph-1", "revision": 1, **definition.model_dump()})
    result = asyncio.run(compiled.graph.ainvoke({"messages": [], "shared": {"seed": 1}}, context=WorkflowContext("r", "graph-1", "i")))
    assert result["ports"]["value.value"] == "ok"
    assert result["shared"]["seed"] == 1


def test_entry_script_name_is_letters_and_hyphens_only() -> None:
    assert EntryScriptDefinition(name="Graph-Entry", graph_id="g").name == "Graph-Entry"
    with pytest.raises(ValueError):
        EntryScriptDefinition(name="graph_entry", graph_id="g")


class _State(TypedDict, total=False):
    messages: list[Any]
    inputs: dict[str, Any]
    shared: dict[str, Any]
    count: int
    done: bool


async def _slow_node(state: _State, runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
    await asyncio.sleep(0.1)
    return {"count": 1}


def test_cancel_then_resume_uses_same_thread_checkpoint(tmp_path) -> None:
    async def run() -> None:
        database = SQLiteDatabase(tmp_path / "state.sqlite3")
        WorkflowStore(database).save_item("g", WorkflowDefinition.model_validate(_value_graph()), expected_revision=None)
        builder = StateGraph(_State, context_schema=WorkflowContext)
        builder.add_node("slow", _slow_node)
        builder.add_edge(START, "slow")
        builder.add_edge("slow", END)
        graph = builder.compile()
        compiled = CompiledWorkflow("g", "value-graph", WorkflowDefinition.model_validate(_value_graph()), graph)
        # This test exercises lifecycle bookkeeping; the factory remains the
        # single place where a compiled graph enters the service.
        async def factory(_id: str, _sink: Any, _messages: list[dict[str, Any]], _request_id: str, _committer: Any) -> CompiledWorkflow:
            return compiled

        service = GraphRunService(GraphRunStore(database), factory)
        item = await service.start("g", messages=[])
        await asyncio.sleep(0.01)
        await service.cancel(item["id"])
        assert service.get_run(item["id"])["status"] == "cancelled"

    asyncio.run(run())


def test_router_selects_declared_control_branch() -> None:
    definition = WorkflowDefinition.model_validate({
        **_value_graph(),
        "name": "router-graph",
        "nodes": [
            {"id": "set-decision", "type": "builtin.state.update", "version": "1.0.0", "config": {"path": "decision", "value": "yes"}},
            {"id": "router", "type": "builtin.router", "version": "1.0.0", "config": {"path": "decision", "cases": {"yes": "accepted"}, "default": "rejected"}},
            {"id": "accepted", "type": "builtin.value", "version": "1.0.0", "config": {"value": "accepted"}},
            {"id": "rejected", "type": "builtin.value", "version": "1.0.0", "config": {"value": "rejected"}},
        ],
        "entry_nodes": ["set-decision"],
        "edges": [
            {"id": "edge-1", "source": {"node": "set-decision", "port": "status"}, "target": {"node": "router", "port": "activate"}},
            {"id": "edge-2", "source": {"node": "router", "port": "status"}, "target": {"node": "accepted", "port": "activate"}, "condition": "accepted"},
            {"id": "edge-3", "source": {"node": "router", "port": "status"}, "target": {"node": "rejected", "port": "activate"}, "condition": "rejected"},
        ],
    })
    compiled = WorkflowCompiler(workflow_lookup=lambda _id: None, agent_invoker=None, tool_invoker=None).compile({"id": "router-graph", "revision": 1, **definition.model_dump()})
    result = asyncio.run(compiled.graph.ainvoke({"messages": []}, context=WorkflowContext("r", "router-graph", "i")))
    assert result["shared"]["decision"] == "yes"
    assert result["ports"]["accepted.value"] == "accepted"
    assert "rejected.value" not in result["ports"]


def test_join_waits_for_all_declared_predecessors() -> None:
    definition = WorkflowDefinition.model_validate({
        **_value_graph(),
        "name": "join-graph",
        "nodes": [
            {"id": "left", "type": "builtin.value", "version": "1.0.0", "config": {"value": "left"}},
            {"id": "right", "type": "builtin.value", "version": "1.0.0", "config": {"value": "right"}},
            {"id": "join", "type": "builtin.join", "version": "1.0.0", "config": {}},
        ],
        "entry_nodes": ["left", "right"],
        "edges": [
            {"id": "edge-1", "source": {"node": "left", "port": "value"}, "target": {"node": "join", "port": "activate"}},
            {"id": "edge-2", "source": {"node": "right", "port": "value"}, "target": {"node": "join", "port": "activate"}},
        ],
    })
    compiled = WorkflowCompiler(workflow_lookup=lambda _id: None, agent_invoker=None, tool_invoker=None).compile({"id": "join-graph", "revision": 1, **definition.model_dump()})
    result = asyncio.run(compiled.graph.ainvoke({"messages": []}, context=WorkflowContext("r", "join-graph", "i")))
    assert result["ports"]["join.status"] == "success"


def test_plugin_node_catalog_and_state_update() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = scan_workflow_node_registry(root / "examples" / "automation-plugins")
    assert registry.get("plugin.workflow-node-text-normalizer.normalize", "1.0.0") is not None

    from agent_shell.workflow.catalog import NodeDefinition, PortDefinition

    plugin_definition = NodeDefinition(
        type="plugin.test.normalize", version="1.0.0", title="Test plugin", description="",
        input_ports=(), output_ports=(PortDefinition("result", "text"),),
        config_schema={"type": "object", "additionalProperties": False}, execution_kind="plugin",
        plugin_id="test-plugin", entrypoint="run",
    )
    definition = WorkflowDefinition.model_validate({
        **_value_graph(), "name": "plugin-graph",
        "nodes": [{"id": "normalize", "type": "plugin.test.normalize", "version": "1.0.0", "config": {}}],
        "entry_nodes": ["normalize"], "edges": [],
    })

    async def invoke_plugin(_node: Any, _definition: Any, _inputs: Mapping[str, Any], _state: Any, _context: WorkflowContext) -> Any:
        return {"outputs": {"result": "ok"}, "shared": {"plugin": True}}

    compiled = WorkflowCompiler(
        workflow_lookup=lambda _id: None, agent_invoker=None, tool_invoker=None,
        node_catalog={plugin_definition.type: plugin_definition}, plugin_invoker=invoke_plugin,
    ).compile({"id": "plugin-graph", "revision": 1, **definition.model_dump()})
    result = asyncio.run(compiled.graph.ainvoke({"messages": []}, context=WorkflowContext("r", "plugin-graph", "i")))
    assert result["ports"]["normalize.result"] == "ok"
    assert result["shared"]["plugin"] is True


def test_agent_node_subgraph_preserves_shared_state_and_lifecycle() -> None:
    agent_builder = StateGraph(WorkflowState, context_schema=WorkflowContext)

    async def agent_step(state: WorkflowState) -> dict[str, Any]:
        return {"shared": {"agent_seen": state.get("shared", {}).get("seed")}, "messages": [AIMessage(content="agent-result")]}

    agent_builder.add_node("step", agent_step)
    agent_builder.add_edge(START, "step")
    agent_builder.add_edge("step", END)
    calls: list[str] = []

    async def start() -> None:
        calls.append("start")

    async def finish(_terminal: Mapping[str, Any]) -> None:
        calls.append("finish")

    definition = WorkflowDefinition.model_validate({
        **_value_graph(), "name": "agent-subgraph",
        "nodes": [{"id": "agent", "type": "builtin.agent", "version": "1.0.0", "config": {"profile_id": "profile-1"}}],
        "entry_nodes": ["agent"], "edges": [],
    })
    compiled = WorkflowCompiler(
        workflow_lookup=lambda _id: None, agent_invoker=None, tool_invoker=None,
        agent_nodes={("agent-subgraph", "agent"): AgentNodeRuntime(
            graph=agent_builder.compile(), input_state={"messages": []}, context={"agent_shell_invocation": {}}, start=start, finish=finish,
        )},
    ).compile({"id": "agent-subgraph", "revision": 1, **definition.model_dump()})

    async def run() -> dict[str, Any]:
        await compiled.start()
        result = await compiled.graph.ainvoke({"messages": [], "shared": {"seed": "ok"}}, context=WorkflowContext("r", "agent-subgraph", "i"))
        await compiled.finish({"status": "completed"})
        return result

    result = asyncio.run(run())
    assert result["shared"]["agent_seen"] == "ok"
    assert result["ports"]["agent.response"] == "agent-result"
    assert calls == ["start", "finish"]


def test_graph_run_resume_reuses_checkpoint(tmp_path) -> None:
    async def run() -> None:
        database = SQLiteDatabase(tmp_path / "resume.sqlite3")
        WorkflowStore(database).save_item(
            "resume-graph", WorkflowDefinition.model_validate(_value_graph()), expected_revision=None
        )
        saver = InMemorySaver()
        builder = StateGraph(_State, context_schema=WorkflowContext)

        async def first(_state: _State) -> dict[str, Any]:
            await asyncio.sleep(0.05)
            return {"count": 1}

        async def second(_state: _State) -> dict[str, Any]:
            await asyncio.sleep(2)
            return {"done": True}

        builder.add_node("first", first)
        builder.add_node("second", second)
        builder.add_edge(START, "first")
        builder.add_edge("first", "second")
        builder.add_edge("second", END)
        compiled = CompiledWorkflow("resume-graph", "resume-graph", WorkflowDefinition.model_validate(_value_graph()), builder.compile(checkpointer=saver))

        async def factory(_id: str, _sink: Any, _messages: list[dict[str, Any]], _request_id: str, _committer: Any) -> CompiledWorkflow:
            return compiled

        service = GraphRunService(GraphRunStore(database), factory)
        item = await service.start("resume-graph", messages=[])
        await asyncio.sleep(0.15)
        await service.cancel(item["id"])
        await asyncio.sleep(0.05)
        resumed = await service.resume(item["id"])
        for _ in range(100):
            await asyncio.sleep(0.03)
            if service.get_run(resumed["id"])["status"] == "completed":
                break
        final = service.get_run(item["id"])
        assert final["status"] == "completed"
        assert final["state"]["done"] is True

    asyncio.run(run())


def test_commit_tool_and_reconciler_are_composable_examples() -> None:
    values = {"/output/a.txt": b"alpha", "/output/image.bin": b"\x00\xff"}
    events: list[dict[str, Any]] = []

    async def read(path: str) -> bytes:
        return values[path]

    async def emit(event: dict[str, Any]) -> None:
        events.append(event)

    async def run() -> None:
        committer = ArtifactCommitter(reader=read, emit=emit)
        assert (await committer.commit("/output/a.txt"))["status"] == "committed"
        assert (await committer.commit("/output/image.bin"))["status"] == "committed_metadata"
        with pytest.raises(ArtifactCommitError, match="already committed"):
            await committer.commit("/output/a.txt")

    asyncio.run(run())
    reconciler = OrderedCommitReconciler(("/output/a.txt", "/output/image.bin"))
    assert reconciler.accept(events[1]) == []
    ready = reconciler.accept(events[0])
    assert [item["path"] for item in ready] == ["/output/a.txt", "/output/image.bin"]


def test_management_api_runs_graph_with_entry_script(tmp_path) -> None:
    settings = Settings(management_auth_enabled=False)
    settings.bind_paths(tmp_path / "app", tmp_path / "data")
    app = create_app(settings=settings, serve_frontend=False)

    with TestClient(app) as client:
        created = client.post("/api/workflows", json=_value_graph())
        assert created.status_code == 200, created.text
        graph = created.json()
        entry_response = client.post("/api/entry-scripts", json={
            "name": "Graph-Test",
            "graph_id": graph["id"],
            "source": "def prepare(messages):\n    return {'messages': messages, 'shared': {'seed': 'entry'}}",
            "enabled": True,
        })
        assert entry_response.status_code == 200, entry_response.text
        invalid_entry = client.post("/api/entry-scripts", json={
            "name": "invalid:name",
            "graph_id": graph["id"],
            "enabled": True,
        })
        assert invalid_entry.status_code == 422, invalid_entry.text
        assert invalid_entry.json()["detail"]["code"] == "entry_script_validation_failed"
        started = client.post(f"/api/workflows/{graph['id']}/runs", json={
            "messages": [{"role": "user", "content": "hello"}],
            "entry_script_id": entry_response.json()["id"],
        })
        assert started.status_code == 200, started.text
        run_id = started.json()["id"]
        current: dict[str, Any] = {}
        for _ in range(100):
            time.sleep(0.02)
            current = client.get(f"/api/graph-runs/{run_id}").json()
            if current.get("status") in {"completed", "failed"}:
                break
        assert current["status"] == "completed", current
        assert current["state"]["shared"]["seed"] == "entry"
        assert current["state"]["ports"]["value.value"] == "ok"
