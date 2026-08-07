from __future__ import annotations

import asyncio

from agent_shell.workflow.compiler import WorkflowCompiler
from agent_shell.workflow.context import WorkflowContext
from agent_shell.runtime.workflow_adapters import as_compiled_subagent


def test_compiled_workflow_runs_without_a_main_agent() -> None:
    record = {
        "id": "workflow-id",
        "public_id": "workflow-echo",
        "name": "Echo",
        "description": "",
        "schema_version": 1,
        "enabled": True,
        "root_interface": {"kind": "chat", "input": "messages", "output": "message"},
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "version": "1.0.0", "config": {}},
            {"id": "echo", "type": "builtin.tool.call", "version": "1.0.0", "config": {"tool_name": "echo", "arguments": {"text": "done"}}},
            {"id": "output", "type": "builtin.output.message", "version": "1.0.0", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "echo", "port": "messages"}},
            {"id": "e2", "source": {"node": "echo", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
        "layout": {},
    }

    async def agent_invoker(_agent_id, _messages, _context):
        return "agent"

    async def tool_invoker(_tool_name, arguments, _state, _context):
        return arguments["text"]

    compiler = WorkflowCompiler(
        workflow_lookup=lambda _workflow_id: None,
        agent_invoker=agent_invoker,
        tool_invoker=tool_invoker,
    )
    compiled = compiler.compile(record)
    result = asyncio.run(
        compiled.graph.ainvoke(
            {"messages": [{"role": "user", "content": "hello"}]},
            context=WorkflowContext(
                request_id="request",
                workflow_id="workflow-id",
                invocation_id="invocation",
            ),
        )
    )
    assert result["messages"][-1].content == "done"
    adapted = as_compiled_subagent(compiled, description="Runs the echo workflow.")
    assert adapted["name"] == "workflow-echo"
    assert adapted["runnable"] is not compiled.graph
    adapted_result = asyncio.run(
        adapted["runnable"].ainvoke(
            {"messages": [{"role": "user", "content": "hello"}]},
            context={"agent_shell_invocation": {"request_id": "request", "id": "invocation"}},
        )
    )
    assert adapted_result["messages"][-1].content == "done"


def test_workflow_call_composes_a_static_child_graph() -> None:
    child = {
        "id": "child-id",
        "public_id": "workflow-child",
        "name": "Child",
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "config": {}},
            {
                "id": "echo",
                "type": "builtin.tool.call",
                "config": {"tool_name": "echo", "arguments": {"text": "child"}},
            },
            {"id": "output", "type": "builtin.output.message", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "echo", "port": "messages"}},
            {"id": "e2", "source": {"node": "echo", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    parent = {
        "id": "parent-id",
        "public_id": "workflow-parent",
        "name": "Parent",
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "config": {}},
            {"id": "child", "type": "builtin.workflow.call", "config": {"workflow_id": "child-id"}},
            {"id": "output", "type": "builtin.output.message", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "child", "port": "messages"}},
            {"id": "e2", "source": {"node": "child", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    records = {child["id"]: child, parent["id"]: parent}

    async def tool_invoker(_name, arguments, _state, _context):
        return arguments["text"]

    compiled = WorkflowCompiler(
        workflow_lookup=records.get,
        agent_invoker=lambda *_args: asyncio.sleep(0, result="agent"),
        tool_invoker=tool_invoker,
    ).compile(parent)
    result = asyncio.run(
        compiled.graph.ainvoke(
            {"messages": [{"role": "user", "content": "hello"}]},
            context=WorkflowContext(
                request_id="request",
                workflow_id="parent-id",
                invocation_id="invocation",
            ),
        )
    )
    assert result["messages"][-1].content == "child"
