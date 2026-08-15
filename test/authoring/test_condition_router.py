from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.condition_router import ConditionRouterError, run_condition_router
from agent_shell.condition_router_packages import ConditionRouterPackageRuntime
from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import AgentShellState
from agent_shell.workflow import admit_workflow_document, compile_workflow
from agent_shell.workflow.topology import validate_workflow_topology


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


def test_condition_router_receives_complete_values_and_converts_state_mutation() -> None:
    async def router(state, context):
        state.setdefault("shared_vars", {})["approved"] = context["prepare"]["approved"]
        return {"activate": ["review", "audit"], "update": {}}

    result = asyncio.run(
        run_condition_router(
            router,
            state={"shared_vars": {"risk": 90}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(
                request_id="request-1",
                workflow={"id": "workflow-1"},
                prepare={"approved": True},
            ),
            allowed_branches={"review", "audit", "otherwise"},
        )
    )

    assert result.activate == ["review", "audit"]
    assert result.update == {"shared_vars": {"risk": 90, "approved": True}}


def test_condition_router_uses_otherwise_for_empty_result_and_rejects_unmapped_keys() -> None:
    async def router(state, context):
        return {"activate": [], "update": {}}
    result = asyncio.run(
        run_condition_router(
            router,
            state={"shared_vars": {}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(),
            allowed_branches={"review", "audit", "otherwise"},
        )
    )
    assert result.activate == ["otherwise"]

    async def invalid(state, context):
        return {"activate": ["otherwise", "review"], "update": {}}
    with pytest.raises(ConditionRouterError):
        asyncio.run(
            run_condition_router(
                invalid,
                state={"shared_vars": {}, "agent_invocations": {}, "files": {}},
                context=WorkflowRuntimeContext(),
                allowed_branches={"review", "audit", "otherwise"},
            )
        )

    async def unmapped(state, context):
        return {"activate": ["missing edge"], "update": {}}
    with pytest.raises(ConditionRouterError):
        asyncio.run(
            run_condition_router(
                unmapped,
                state={"shared_vars": {}, "agent_invocations": {}, "files": {}},
                context=WorkflowRuntimeContext(),
                allowed_branches={"review", "audit", "otherwise"},
            )
        )


def test_condition_router_package_loads_local_modules_and_materializes_async_route(
    tmp_path: Path,
) -> None:
    package_id = "44444444-4444-4444-8444-444444444444"
    folder_name = f"{ROUTER_ID}--threshold-router--{package_id}"
    package_dir = tmp_path / "packages" / "condition-router" / folder_name
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": package_id,
                "family": "workflow-node",
                "adapter": "condition-router",
                "name": "Threshold router",
                "description": "Routes by a configured threshold.",
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "integer", "title": "Threshold"}
                    },
                    "required": ["threshold"],
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "main.py").write_text(
        "from .routing import build_route\n"
        "def create_router(config):\n"
        "    return build_route(config['threshold'])\n",
        encoding="utf-8",
    )
    (package_dir / "routing.py").write_text(
        "def build_route(threshold):\n"
        "    async def route(state, context):\n"
        "        branch = 'review' if state['shared_vars']['risk'] >= threshold else 'otherwise'\n"
        "        return {'activate': [branch], 'update': {}}\n"
        "    return route\n",
        encoding="utf-8",
    )
    runtime = ConditionRouterPackageRuntime(
        request_id="request-1",
        packages_dir=tmp_path / "packages",
        runtime_root=tmp_path / "runtime",
    )
    route = runtime.router_for(
        "router-node",
        ROUTER_ID,
        {"folder": folder_name, "config": {"threshold": 80}},
    )

    result = asyncio.run(
        run_condition_router(
            route,
            state={"shared_vars": {"risk": 90}, "agent_invocations": {}, "files": {}},
            context=WorkflowRuntimeContext(),
            allowed_branches={"review", "otherwise"},
        )
    )

    assert result.activate == ["review"]
    asyncio.run(runtime.close())


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
    async def router(state, context):
        return {
            "activate": ["review", "audit"],
            "update": {"shared_vars": {"routed": True}},
        }
    missing_otherwise = document.model_copy(deep=True)
    missing_otherwise.definition.edges = [
        edge
        for edge in missing_otherwise.definition.edges
        if edge.branch_key != "otherwise"
    ]
    assert any(
        issue.code == "workflow.condition_router_branch_missing"
        and issue.message_args == {"branch_key": "otherwise"}
        for issue in validate_workflow_topology(
            missing_otherwise,
            condition_routers={"router": router},
        )
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
