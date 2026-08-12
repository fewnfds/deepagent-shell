from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_shell.plugins.session_recorder.contracts import SessionRecorderBlock
from agent_shell.plugins.session_recorder.middleware import SessionRecorderMiddleware


def test_session_recorder_stores_a_transformed_detached_copy_with_provenance() -> None:
    state = {"messages": [HumanMessage(content="original")], "shared_vars": {}}
    middleware = SessionRecorderMiddleware(
        SessionRecorderBlock(
            name="Recorder",
            custom_transform_enabled=True,
            custom_transform_source=(
                "def transform(messages, read_file, config, state, context):\n"
                "    messages.append({'role': 'assistant', 'content': context.marker})\n"
                "    return messages\n"
            ),
        ),
        backend=None,
        agent_scope="main_agent",
        agent_id="agent-id",
        agent_name="Research Agent",
        workflow_node_id="agent-node",
    )

    update = middleware.after_agent(
        state,
        SimpleNamespace(context=SimpleNamespace(marker="recorded")),
    )

    session_id, record = next(iter(update["agent_sessions"].items()))
    assert record == {
        "session_id": session_id,
        "agent_scope": "main_agent",
        "agent_id": "agent-id",
        "agent_name": "Research Agent",
        "workflow_node_id": "agent-node",
        "messages": [
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "recorded"},
        ],
    }
    assert len(state["messages"]) == 1
    assert state["messages"][0].content == "original"


def test_session_recorder_preserves_complete_tool_conversation_without_run_ids() -> None:
    state = {
        "messages": [
            HumanMessage(content="inspect the file"),
            AIMessage(
                content="",
                id="provider-run-id",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"path": "/result.txt"},
                        "id": "tool-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content="contents",
                tool_call_id="tool-call-1",
                id="tool-message-id",
            ),
            AIMessage(content="The file contains contents.", id="final-run-id"),
        ]
    }
    middleware = SessionRecorderMiddleware(
        SessionRecorderBlock(name="Recorder"),
        backend=None,
        agent_scope="main_agent",
        agent_id="agent-id",
        agent_name="Research Agent",
        workflow_node_id="agent-node",
    )

    update = middleware.after_agent(
        state,
        SimpleNamespace(context=None),
    )

    record = next(iter(update["agent_sessions"].values()))
    assert record["messages"] == [
        {"role": "user", "content": "inspect the file"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "id": "tool-call-1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/result.txt"}',
                    },
                }
            ],
            "content": "",
        },
        {
            "role": "tool",
            "tool_call_id": "tool-call-1",
            "content": "contents",
        },
        {"role": "assistant", "content": "The file contains contents."},
    ]
