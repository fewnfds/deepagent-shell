from __future__ import annotations

from .support import *

def test_selected_todo_middleware_updates_state_and_uses_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    ToolCallingFakeModel.bound_tool_names = []
    ToolCallingFakeModel.bound_tool_descriptions = {}
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_todos",
                        "args": {
                            "todos": [
                                {"content": "verify runtime", "status": "in_progress"}
                            ]
                        },
                        "id": "call-todo",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="todo completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        todo = client.post(
            "/api/blocks/todo-list",
            json={
                "name": "Runtime Todo",
                "system_prompt_override": "CUSTOM TODO INSTRUCTIONS",
                "tool_description_override": "CUSTOM TODO DESCRIPTION",
            },
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {"type": "todo-list", "block_id": todo["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Plan the work."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "todo completed"
    assert set(ToolCallingFakeModel.bound_tool_names) == {"write_todos", "read_file"}
    assert ToolCallingFakeModel.bound_tool_descriptions["write_todos"] == (
        "CUSTOM TODO DESCRIPTION"
    )
    assert "Reads a file from the filesystem" in (
        ToolCallingFakeModel.bound_tool_descriptions["read_file"]
    )
    assert len(ToolCallingFakeModel.seen_messages) == 2
    system_messages = [
        message
        for message in ToolCallingFakeModel.seen_messages[0]
        if message.type == "system"
    ]
    assert len(system_messages) == 1
    assert system_messages[0].text.strip() == "CUSTOM TODO INSTRUCTIONS"
    assert "Filesystem Tools" not in system_messages[0].text
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert len(tool_results) == 1
    assert tool_results[0].name == "write_todos"

def test_selected_middleware_prompt_hooks_follow_product_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data" / "resources" / "skills" / "ordered-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: ordered-skill\ndescription: Order test.\n---\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="ordered")])
    marker_source = (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "from langchain_core.messages import SystemMessage\n"
        "class MarkerMiddleware(AgentMiddleware):\n"
        "    def _mark(self, request):\n"
        "        text = request.system_message.text if request.system_message else ''\n"
        "        return request.override(system_message=SystemMessage(content=text + '\\nCUSTOM'))\n"
        "    def wrap_model_call(self, request, handler):\n"
        "        return handler(self._mark(request))\n"
        "    async def awrap_model_call(self, request, handler):\n"
        "        return await handler(self._mark(request))\n"
        "middleware = MarkerMiddleware()\n"
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        todo = client.post(
            "/api/blocks/todo-list",
            json={"name": "Ordered Todo", "system_prompt_override": "TODO"},
        ).json()
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Ordered filesystem", "system_prompt_override": "FILESYSTEM"},
        ).json()
        skill = client.post(
            "/api/blocks/skill",
            json={
                "name": "Ordered Skill",
                "skills": ["ordered-skill"],
                "instruction_override": (
                    "SKILL\n{skills_locations}\n{skills_load_warnings}\n{skills_list}"
                ),
            },
        ).json()
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Ordered custom Middleware",
                "middlewares": [
                    {"name": "Final marker", "enabled": True, "source": marker_source}
                ],
            },
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        main_agent, "filesystem", filesystem["id"]
                    ),
                    {"type": "todo-list", "block_id": todo["id"]},
                    {"type": "skill", "block_id": skill["id"]},
                    {"type": "custom-middleware", "block_id": custom["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Check order."}],
            },
        )

    assert response.status_code == 200, response.text
    system = next(
        message for message in ToolCallingFakeModel.seen_messages[0] if message.type == "system"
    ).text
    assert system.index("SKILL") < system.index("FILESYSTEM")
    assert system.index("FILESYSTEM") < system.index("TODO")
    assert system.index("TODO") < system.index("CUSTOM")
