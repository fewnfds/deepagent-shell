from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.agent_runtime import AgentRuntime
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

    result = asyncio.run(
        run_workflow_prepare(
            {
                "name": "Prepare",
                "prepare_source": (
                    "async def prepare(input):\n"
                    "    input['workflow']['id'] = 'changed'\n"
                    "    return {'context': {'agent_name': input['agents']['node-1']['main_agent']['name']}}\n"
                ),
            },
            input_value=input_value,
        )
    )

    assert result.context == {"agent_name": "Agent"}
    assert input_value["workflow"]["id"] == "workflow-1"


def test_workflow_prepare_rejects_undeclared_result_fields() -> None:
    with pytest.raises(WorkflowPrepareError, match="workflow prepare failed"):
        asyncio.run(
            run_workflow_prepare(
                {
                    "name": "Prepare",
                    "prepare_source": (
                        "async def prepare(input):\n"
                        "    return {'context': {}, 'state': {}}\n"
                    ),
                },
                input_value={"request": {}, "workflow": {}, "agents": {}},
            )
        )


def test_workflow_prepare_runs_after_all_resolution_and_before_agent_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    agent_a = "11111111-1111-4111-8111-111111111111"
    agent_b = "22222222-2222-4222-8222-222222222222"

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
                input_state={"messages": [], "shared_vars": {}, "agent_sessions": {}},
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

    async def prepare(_block, *, input_value):
        events.append("prepare")
        assert set(input_value["agents"]) == {"agent-1", "agent-2"}
        return type("Result", (), {"context": {"prepared": True}})()

    monkeypatch.setattr("agent_shell.runtime.agent_runtime.run_workflow_prepare", prepare)
    blocks = type(
        "Blocks",
        (),
        {
            "get_block_internal": staticmethod(
                lambda *_args: {
                    "id": "prepare-1",
                    "name": "Prepare",
                    "enabled": True,
                    "prepare_source": "async def prepare(input):\n    return {'context': {}}\n",
                    "python_requirements": [],
                }
            )
        },
    )()
    runtime = Runtime(Builder(), object(), blocks=blocks)  # type: ignore[arg-type]
    payload = {
        "definition": {
            "schema_version": 1,
            "state_contract": "agent-shell.workflow.messages.v1",
            "nodes": [
                {"id": "start", "type": "start", "type_version": 1, "config": {}},
                {"id": "agent-1", "type": "agent", "type_version": 1, "config": {"main_agent_id": agent_a}},
                {"id": "agent-2", "type": "agent", "type_version": 1, "config": {"main_agent_id": agent_b}},
                {"id": "end", "type": "end", "type_version": 1, "config": {}},
            ],
            "edges": [
                {"id": "edge-1", "source": "start", "source_handle": "next", "target": "agent-1", "target_handle": "in"},
                {"id": "edge-2", "source": "agent-1", "source_handle": "next", "target": "agent-2", "target_handle": "in"},
                {"id": "edge-3", "source": "agent-2", "source_handle": "next", "target": "end", "target_handle": "in"},
            ],
        },
        "layout": {
            "nodes": {
                "start": {"x": 0, "y": 0},
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
                "state_mode": "isolated",
                "workflow_prepare_id": "prepare-1",
            },
        )
    )

    assert events == [
        f"resolve:{agent_a}",
        f"resolve:{agent_b}",
        "prepare",
        f"build:{agent_a}",
        f"build:{agent_b}",
    ]
    assert execution["context"].prepare == {"prepared": True}
