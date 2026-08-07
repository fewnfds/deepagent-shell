from __future__ import annotations

from .support import *

def test_selected_skill_is_mounted_on_shared_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data" / "resources" / "skills" / "outline"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: outline\ndescription: Outline a document.\n---\n"
        "# Outline workflow\nUse three headings.\n",
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
                        "name": "read_file",
                        "args": {"file_path": "/skills/outline/SKILL.md"},
                        "id": "call-read-skill",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="skill completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        filesystem = client.post(
            "/api/blocks/filesystem", json={"name": "Skill filesystem"}
        ).json()
        skill = client.post(
            "/api/blocks/skill",
            json={"name": "Runtime skill", "skills": ["outline"]},
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        main_agent, "filesystem", filesystem["id"]
                    ),
                    {"type": "skill", "block_id": skill["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Use the outline skill."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "skill completed"
    system_messages = [
        message
        for message in ToolCallingFakeModel.seen_messages[0]
        if message.type == "system"
    ]
    assert any("outline" in message.text for message in system_messages)
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert len(tool_results) == 1
    assert "Use three headings" in str(tool_results[0].content)

def test_missing_selected_skill_fails_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data" / "resources" / "skills" / "disappearing"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: disappearing\ndescription: Runtime validation.\n---\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        filesystem = client.post(
            "/api/blocks/filesystem", json={"name": "Missing Skill filesystem"}
        ).json()
        skill = client.post(
            "/api/blocks/skill",
            json={"name": "Missing runtime Skill", "skills": ["disappearing"]},
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        main_agent, "filesystem", filesystem["id"]
                    ),
                    {"type": "skill", "block_id": skill["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        skill_file.unlink()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Do not call provider."}],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "middleware_materialization_failed"
    assert str(skill_file) not in response.text
    assert ToolCallingFakeModel.seen_messages == []
