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
        primary = create_primary(client)
        todo = client.post(
            "/api/blocks/todo-list",
            json={
                "name": "Runtime Todo",
                "system_prompt_override": "CUSTOM TODO INSTRUCTIONS",
                "tool_description_override": "CUSTOM TODO DESCRIPTION",
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "todo-list", "block_id": todo["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Plan the work."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "todo completed"
    assert ToolCallingFakeModel.bound_tool_names == ["write_todos", "read_file"]
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
    assert system_messages[0].text == "CUSTOM TODO INSTRUCTIONS"
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
        primary = create_primary(client)
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
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
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
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Check order."}],
            },
        )

    assert response.status_code == 200, response.text
    system = next(
        message for message in ToolCallingFakeModel.seen_messages[0] if message.type == "system"
    ).text
    assert system.index("TODO") < system.index("SKILL")
    assert system.index("SKILL") < system.index("FILESYSTEM")
    assert system.index("FILESYSTEM") < system.index("CUSTOM")

def test_selected_custom_middleware_executes_enabled_recipe_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    construction_count = tmp_path / "middleware-construction-count.txt"
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="middleware completed")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        middleware = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Runtime middleware",
                "middlewares": [
                    {
                        "name": "Disabled recipe",
                        "enabled": False,
                        "source": (
                            "raise RuntimeError('disabled recipe executed')\n"
                            "middleware = None\n"
                        ),
                    },
                    {
                        "name": "Email redaction",
                        "enabled": True,
                        "source": (
                            "from pathlib import Path\n"
                            f"counter = Path({str(construction_count)!r})\n"
                            "count = int(counter.read_text()) if counter.exists() else 0\n"
                            "counter.write_text(str(count + 1))\n"
                            "from langchain.agents.middleware import PIIMiddleware\n"
                            "middleware = [PIIMiddleware(\n"
                            "    'email', strategy='redact', apply_to_input=True\n"
                            ")]\n"
                        ),
                    },
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": middleware["id"]},
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
                    {"role": "user", "content": "Contact me at user@example.com"}
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert construction_count.read_text(encoding="utf-8") == "1"
    assert response.json()["choices"][0]["message"]["content"] == "middleware completed"
    human_message = next(
        message
        for message in ToolCallingFakeModel.seen_messages[0]
        if message.type == "human"
    )
    assert "user@example.com" not in human_message.text

def test_custom_middleware_construction_failure_is_safe_and_pre_provider(
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
        middleware = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Broken runtime middleware",
                "middlewares": [
                    {
                        "name": "Broken recipe",
                        "enabled": True,
                        "source": (
                            "raise RuntimeError('private construction details')\n"
                            "middleware = None\n"
                        ),
                    }
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": middleware["id"]},
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
    assert response.json()["error"]["code"] == "custom_middleware_execution_failed"
    assert "private construction details" not in response.text
    assert ToolCallingFakeModel.seen_messages == []

def test_primary_duplicate_runtime_middleware_name_is_reported_pre_provider(
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
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Conflicting Primary middleware",
                "middlewares": [
                    {
                        "name": "Two runtime names",
                        "enabled": True,
                        "source": duplicate_runtime_middleware_source(),
                    }
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": custom["id"]},
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
    error = response.json()["error"]
    assert error["code"] == "agent_middleware_name_conflict"
    assert "Primary Agent" in error["message"]
    assert "shared_runtime_name" in error["message"]
    assert ToolCallingFakeModel.seen_messages == []

def test_subagent_duplicate_runtime_middleware_name_identifies_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    models = iter(
        [
            ToolCallingFakeModel(responses=[AIMessage(content="parent must not run")]),
            ToolCallingFakeModel(responses=[AIMessage(content="child must not run")]),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Inherited conflicting middleware",
                "middlewares": [
                    {
                        "name": "Two inherited runtime names",
                        "enabled": True,
                        "source": duplicate_runtime_middleware_source(),
                    }
                ],
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Conflict delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": custom["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "conflicted_worker",
                        "description": "Uses the inherited conflicting Middleware.",
                        "subagent_override_id": "",
                    }
                ],
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
    error = response.json()["error"]
    assert error["code"] == "agent_middleware_name_conflict"
    assert "Subagent conflicted_worker" in error["message"]
    assert "shared_runtime_name" in error["message"]
    assert ToolCallingFakeModel.seen_messages == []
