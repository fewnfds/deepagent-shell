from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.agent_runtime import AgentRuntime
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import AgentShellState
from agent_shell.validation.assembly import StaticAssembly
from agent_shell.workflow import admit_workflow_document
from agent_shell.workflow_prepare import WorkflowPrepareError, run_workflow_prepare


def test_workflow_prepare_receives_a_detached_snapshot_and_returns_context() -> None:
    input_value = {
        "request": {"request_id": "request-1", "messages": [], "messages_sha": "sha"},
        "workflow": {"id": "workflow-1"},
        "agents": {"node-1": {"main_agent": {"name": "Agent"}}},
    }

    async def prepare(input):
        input["workflow"]["id"] = "changed"
        return {
            "context": {
                "agent_name": input["agents"]["node-1"]["main_agent"]["name"]
            }
        }

    result = asyncio.run(run_workflow_prepare(prepare, input_value=input_value))

    assert result.context == {"agent_name": "Agent"}
    assert input_value["workflow"]["id"] == "workflow-1"


def test_workflow_prepare_rejects_undeclared_result_fields() -> None:
    async def prepare(_input):
        return {"context": {}, "state": {}}

    with pytest.raises(WorkflowPrepareError, match="workflow prepare failed"):
        asyncio.run(
            run_workflow_prepare(
                prepare,
                input_value={"request": {}, "workflow": {}, "agents": {}},
            )
        )


def test_workflow_prepare_runs_after_all_resolution_and_before_agent_builds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    agent_a = "11111111-1111-4111-8111-111111111111"
    agent_b = "22222222-2222-4222-8222-222222222222"
    prepare_id = "33333333-3333-4333-8333-333333333333"
    router_id = "44444444-4444-4444-8444-444444444444"

    class MiddlewareRuntime:
        async def close(self) -> None:
            return None

    class Builder:
        def resolve(self, main_agent_id: str, **_kwargs) -> StaticAssembly:
            events.append(f"resolve:{main_agent_id}")
            return StaticAssembly(
                main_agent={"id": main_agent_id, "name": main_agent_id},
                references={},
                blocks={},
                filesystem_mode="configured-shared",
                disabled_capabilities=frozenset(),
                subagents=(),
                subagent_nodes={},
            )

        def script_dependency_metadata(self, *_args) -> dict[str, str]:
            return {"dependency_status": "ready"}

        async def build_resolved(self, assembly, _messages, **_kwargs) -> BuiltAgent:
            agent_id = str(assembly.main_agent["id"])
            events.append(f"build:{agent_id}")

            def answer(_state: AgentShellState) -> dict[str, list[AIMessage]]:
                return {"messages": [AIMessage(content=agent_id)]}

            graph = (
                StateGraph(AgentShellState)
                .add_node("answer", answer)
                .add_edge(START, "answer")
                .add_edge("answer", END)
                .compile()
            )
            return BuiltAgent(
                graph=graph,
                input_state={"messages": [], "shared_vars": {}},
                output_config={},
                agent_id=agent_id,
                agent_name=agent_id,
                subagent_profile_ids={},
                middleware_runtime=MiddlewareRuntime(),  # type: ignore[arg-type]
            )

        async def close_failed_build(self) -> None:
            return None

    class Runtime(AgentRuntime):
        def _execution(self, built: BuiltAgent, **kwargs):
            return {"built": built, **kwargs}

    class PrepareRuntime:
        def __init__(self, **_kwargs) -> None:
            pass

        def prepare_for(self, owner_id, reference):
            events.append("prepare-factory")
            assert owner_id == prepare_id
            assert reference["folder"] == prepare_id

            async def prepare(input):
                events.append("prepare")
                assert set(input["agents"]) == {"agent-1", "agent-2"}
                return {"context": {"prepared": True}}

            return prepare

        async def close(self) -> None:
            events.append("prepare-close")

    class RouterRuntime:
        def __init__(self, **_kwargs) -> None:
            pass

        def router_for(self, node_id, owner_id, reference):
            events.append("router-factory")
            assert node_id == "router"
            assert owner_id == router_id
            assert reference["folder"] == router_id

            async def route(state, context):
                events.append("router-call")
                assert state["shared_vars"] == {}
                assert context["prepare"] == {"prepared": True}
                return {"activate": ["otherwise"], "update": {}}

            return route

        async def close(self) -> None:
            return None

    original_from_request = WorkflowRuntimeContext.from_request

    def from_request(_cls, raw_messages, **kwargs):
        events.append("context")
        return original_from_request(raw_messages, **kwargs)

    monkeypatch.setattr(
        WorkflowRuntimeContext,
        "from_request",
        classmethod(from_request),
    )
    monkeypatch.setattr(
        "agent_shell.runtime.agent_runtime.WorkflowPreparePackageRuntime",
        PrepareRuntime,
    )
    monkeypatch.setattr(
        "agent_shell.runtime.agent_runtime.ConditionRouterPackageRuntime",
        RouterRuntime,
    )

    def get_block_internal(block_type, _block_id):
        if block_type == "workflow-prepare":
            return {
                "id": prepare_id,
                "name": "Prepare",
                "python_package": {
                    "folder": prepare_id,
                    "editable_files": ["main.py"],
                },
            }
        if block_type == "condition-router":
            return {
                "id": router_id,
                "name": "Router",
                "python_package": {
                    "folder": router_id,
                    "editable_files": ["main.py"],
                },
            }
        return None

    blocks = type(
        "Blocks",
        (),
        {"get_block_internal": staticmethod(get_block_internal)},
    )()
    runtime = Runtime(
        Builder(),
        object(),
        blocks=blocks,
        python_packages_dir=tmp_path / "packages",
        runtime_dir=tmp_path / "runtime",
    )  # type: ignore[arg-type]
    payload = {
        "definition": {
            "schema_version": 1,
            "state_contract": "agent-shell.workflow.agent-invocations.v1",
            "nodes": [
                {"id": "start", "type": "start", "type_version": 1, "config": {}},
                {
                    "id": "router",
                    "type": "condition-router",
                    "type_version": 1,
                    "config": {"condition_router_id": router_id},
                },
                {"id": "agent-1", "type": "agent", "type_version": 1, "config": {"main_agent_id": agent_a}},
                {"id": "agent-2", "type": "agent", "type_version": 1, "config": {"main_agent_id": agent_b}},
                {"id": "end", "type": "end", "type_version": 1, "config": {}},
            ],
            "edges": [
                {"id": "edge-1", "source": "start", "source_handle": "next", "target": "router", "target_handle": "in"},
                {"id": "edge-2", "source": "router", "source_handle": "branch", "target": "agent-1", "target_handle": "in", "branch_key": "first"},
                {"id": "edge-3", "source": "router", "source_handle": "branch", "target": "agent-2", "target_handle": "in", "branch_key": "second"},
                {"id": "edge-4", "source": "router", "source_handle": "branch", "target": "end", "target_handle": "in", "branch_key": "otherwise"},
                {"id": "edge-5", "source": "agent-1", "source_handle": "next", "target": "end", "target_handle": "in"},
                {"id": "edge-6", "source": "agent-2", "source_handle": "next", "target": "end", "target_handle": "in"},
            ],
        },
        "layout": {
            "nodes": {
                "start": {"x": 0, "y": 0},
                "router": {"x": 100, "y": 0},
                "agent-1": {"x": 200, "y": 0},
                "agent-2": {"x": 400, "y": 0},
                "end": {"x": 600, "y": 0},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }
    admission, document = admit_workflow_document(payload)
    assert admission.valid is True
    assert document is not None

    execution = asyncio.run(
        runtime.start_workflow(
            document,
            [{"role": "user", "content": "Run."}],
            workflow_filesystem_id="filesystem-1",
            workflow_snapshot={
                "id": "workflow-1",
                "workflow_prepare_id": prepare_id,
            },
        )
    )
    asyncio.run(
        execution["graph"].ainvoke(
            execution["input_state"],
            context=execution["context"],
        )
    )

    assert events == [
        f"resolve:{agent_a}",
        f"resolve:{agent_b}",
        "prepare-factory",
        "prepare",
        "prepare-close",
        "context",
        "router-factory",
        f"build:{agent_a}",
        f"build:{agent_b}",
        "router-call",
    ]
    assert execution["context"].prepare == {"prepared": True}
