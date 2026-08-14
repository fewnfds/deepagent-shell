from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.condition_router import (
    ConditionRouterBlock,
    ConditionRouterError,
    run_condition_router,
)
from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import AgentShellState
from agent_shell.workflow import admit_workflow_document, compile_workflow


ROUTER_ID = "11111111-1111-4111-8111-111111111111"
AGENT_A = "22222222-2222-4222-8222-222222222222"
AGENT_B = "33333333-3333-4333-8333-333333333333"


class _MiddlewareRuntime:
    async def close(self) -> None:
        return None


def _built_agent(agent_id: str, content: str) -> BuiltAgent:
    graph = (
        StateGraph(AgentShellState)
        .add_node(
            "answer",
            lambda _state: {"messages": [AIMessage(content=content)]},
        )
        .add_edge(START, "answer")
        .add_edge("answer", END)
        .compile()
    )
    return BuiltAgent(
        graph=graph,
        input_state={"messages": [], "shared_vars": {}},
        output_config={},
        agent_id=agent_id,
        agent_name=content,
        subagent_profile_ids={},
        middleware_runtime=_MiddlewareRuntime(),  # type: ignore[arg-type]
    )


def _configuration(source: str) -> ConditionRouterBlock:
    return ConditionRouterBlock(
        name="Risk routing",
        branches=[
            {"key": "review", "label": "Manual review"},
            {"key": "audit", "label": "Audit"},
            {"key": "otherwise", "label": "Otherwise"},
        ],
        route_source=source,
    )


def test_condition_router_receives_complete_values_and_converts_state_mutation() -> None:
    router = _configuration(
        "async def route(state, context):\n"
        "    state.setdefault('shared_vars', {})['approved'] = context['prepare']['approved']\n"
        "    return {'activate': ['review', 'audit'], 'update': {}}\n"
    )

    result = asyncio.run(
        run_condition_router(
            router.model_dump(mode="python"),
            state={"shared_vars": {"risk": 90}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(
                request_id="request-1",
                workflow={"id": "workflow-1"},
                prepare={"approved": True},
            ),
        )
    )

    assert result.activate == ["review", "audit"]
    assert result.update == {"shared_vars": {"risk": 90, "approved": True}}


def test_condition_router_requires_explicit_otherwise_and_uses_it_for_empty_result() -> None:
    with pytest.raises(ValueError, match="exactly one otherwise"):
        ConditionRouterBlock(
            name="Invalid",
            branches=[{"key": "review", "label": "Review"}],
        )

    router = _configuration(
        "async def route(state, context):\n"
        "    return {'activate': [], 'update': {}}\n"
    )
    result = asyncio.run(
        run_condition_router(
            router.model_dump(mode="python"),
            state={"shared_vars": {}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(),
        )
    )
    assert result.activate == ["otherwise"]

    invalid = _configuration(
        "async def route(state, context):\n"
        "    return {'activate': ['otherwise', 'review'], 'update': {}}\n"
    )
    with pytest.raises(ConditionRouterError):
        asyncio.run(
            run_condition_router(
                invalid.model_dump(mode="python"),
                state={"shared_vars": {}, "agent_invocations": {}, "files": {}},
                context=WorkflowRuntimeContext(),
            )
        )


def test_compiler_uses_command_for_named_multi_branch_routing() -> None:
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
                    "config": {"condition_router_id": ROUTER_ID},
                },
                {"id": "agent-a", "type": "agent", "type_version": 1, "config": {"main_agent_id": AGENT_A}},
                {"id": "agent-b", "type": "agent", "type_version": 1, "config": {"main_agent_id": AGENT_B}},
                {"id": "end", "type": "end", "type_version": 1, "config": {}},
            ],
            "edges": [
                {"id": "start-router", "source": "start", "source_handle": "next", "target": "router", "target_handle": "in"},
                {"id": "review", "source": "router", "source_handle": "branch", "target": "agent-a", "target_handle": "in", "branch_key": "review"},
                {"id": "audit", "source": "router", "source_handle": "branch", "target": "agent-b", "target_handle": "in", "branch_key": "audit"},
                {"id": "otherwise", "source": "router", "source_handle": "branch", "target": "end", "target_handle": "in", "branch_key": "otherwise"},
                {"id": "agent-a-end", "source": "agent-a", "source_handle": "next", "target": "end", "target_handle": "in"},
                {"id": "agent-b-end", "source": "agent-b", "source_handle": "next", "target": "end", "target_handle": "in"},
            ],
        },
        "layout": {},
    }
    admission, document = admit_workflow_document(payload)
    assert admission.valid is True
    assert document is not None
    router = _configuration(
        "async def route(state, context):\n"
        "    return {'activate': ['review', 'audit'], 'update': {'shared_vars': {'routed': True}}}\n"
    )
    graph = compile_workflow(
        document,
        node_agents={
            "agent-a": _built_agent(AGENT_A, "agent-a"),
            "agent-b": _built_agent(AGENT_B, "agent-b"),
        },
        condition_routers={"router": router},
    )

    result = asyncio.run(
        graph.ainvoke(
            {"shared_vars": {}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(workflow={"id": "workflow-1"}),
        )
    )

    assert result["shared_vars"] == {"routed": True}
    assert {
        record["workflow_node_id"]
        for record in result["agent_invocations"].values()
    } == {"agent-a", "agent-b"}
