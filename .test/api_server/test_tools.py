from __future__ import annotations

from .support import *

def test_selected_custom_tool_runs_in_the_real_agent_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "ping.py").write_text(
        "from langchain_core.tools import tool\n"
        "@tool\n"
        "def ping(message: str) -> str:\n"
        "    \"\"\"Return a deterministic acknowledgement.\"\"\"\n"
        "    return f'pong: {message}'\n",
        encoding="utf-8",
    )
    (tools_dir / "unselected.py").write_text(
        "raise RuntimeError('unselected module was imported')\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    ToolCallingFakeModel.bound_tool_names = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ping",
                        "args": {"message": "hello"},
                        "id": "call-ping",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tool completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        tools = client.post(
            "/api/blocks/custom-tool",
            json={"name": "Runtime tools", "tools": ["ping"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-tool", "block_id": tools["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Use ping."}],
            },
        )
        session_id = response.headers["x-agent-session-id"]
        session = client.get(f"/api/agent-sessions/{session_id}").json()
        session_listing = client.get("/api/agent-sessions").json()

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "tool completed"
    assert ToolCallingFakeModel.bound_tool_names == ["read_file", "ping"]
    assert len(ToolCallingFakeModel.seen_messages) == 2
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert [message.content for message in tool_results] == ["pong: hello"]
    assert session["session_id"] == session_id
    assert session["runs"][0]["status"] == "completed"
    assert session["runs"][0]["response_text"] == "tool completed"
    timeline_kinds = [item["kind"] for item in session["runs"][0]["timeline"]]
    assert timeline_kinds.count("model_request") == 2
    assert session_listing["items"][0]["model_call_count"] == 2
    assert "tool_call" in timeline_kinds
    assert "tool_result" in timeline_kinds

def test_selected_custom_tool_can_run_in_two_consecutive_model_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "ping.py").write_text(
        "from langchain_core.tools import tool\n"
        "@tool\n"
        "def ping(message: str) -> str:\n"
        "    \"\"\"Return a deterministic acknowledgement.\"\"\"\n"
        "    return f'pong: {message}'\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ping",
                        "args": {"message": "first"},
                        "id": "call-first",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ping",
                        "args": {"message": "second"},
                        "id": "call-second",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="two tools completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        tools = client.post(
            "/api/blocks/custom-tool",
            json={"name": "Two-step tools", "tools": ["ping"]},
        ).json()
        prompt = client.post(
            "/api/blocks/system-prompt",
            json={"name": "Loop prompt", "system_prompt": "AGENT LOOP"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-tool", "block_id": tools["id"]},
                    {"type": "system-prompt", "block_id": prompt["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "system", "content": "CLIENT HEAD"},
                    {
                        "role": "user",
                        "content": "Use ping twice.",
                    },
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "two tools completed"
    assert len(ToolCallingFakeModel.seen_messages) == 3
    for seen in ToolCallingFakeModel.seen_messages:
        system_messages = [item.text for item in seen if item.type == "system"]
        assert system_messages[0] == "AGENT LOOP"
        assert system_messages[1] == "CLIENT HEAD"
        assert "Filesystem Tools" not in system_messages[0]
        assert sum(item.text == "AGENT LOOP" for item in seen) == 1
    first_result = next(
        item
        for item in ToolCallingFakeModel.seen_messages[1]
        if isinstance(item, ToolMessage)
    )
    second_result = next(
        item
        for item in ToolCallingFakeModel.seen_messages[2]
        if isinstance(item, ToolMessage) and item.tool_call_id == "call-second"
    )
    assert first_result.content == "pong: first"
    assert second_result.content == "pong: second"

def test_missing_selected_custom_tool_fails_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        tools = client.post(
            "/api/blocks/custom-tool",
            json={"name": "Missing runtime tool", "tools": ["missing_tool"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-tool", "block_id": tools["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tool_materialization_not_found"
    assert ToolCallingFakeModel.seen_messages == []

def test_cross_capability_tool_name_conflict_fails_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "conflicting_todo.py").write_text(
        "from langchain_core.tools import tool\n"
        "RUNTIME_TOOL_NAME = 'write_todos'\n"
        "@tool(RUNTIME_TOOL_NAME)\n"
        "def dynamic_todo_conflict(value: str) -> str:\n"
        "    \"\"\"Conflict deliberately with TodoListMiddleware.\"\"\"\n"
        "    return value\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        todo = client.post(
            "/api/blocks/todo-list",
            json={"name": "Conflicting Todo"},
        ).json()
        tools = client.post(
            "/api/blocks/custom-tool",
            json={"name": "Conflicting tools", "tools": ["conflicting_todo"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "todo-list", "block_id": todo["id"]},
                    {"type": "custom-tool", "block_id": tools["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "agent_tool_name_conflict"
    assert ToolCallingFakeModel.seen_messages == []
