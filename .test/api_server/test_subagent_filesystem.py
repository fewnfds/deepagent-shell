from __future__ import annotations

from .support import *


def test_subagent_runs_without_project_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        bound_tool_names: ClassVar[list[str]] = []

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Complete the isolated task.",
                            "subagent_type": "worker",
                        },
                        "id": "call-no-filesystem-subagent",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="parent completed"),
        ]
    )
    child_model = ChildModel(responses=[AIMessage(content="child completed")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, _http_clients: (
                child_model if block["name"] == "No filesystem child" else parent_model
            ),
        )
        parent = create_primary(client, include_filesystem=False)
        child_model_block = client.post(
            "/api/blocks/model",
            json={
                "name": "No filesystem child",
                "provider": "openai",
                "base_url": "https://provider.example/v1",
                "credential": "child-provider-secret",
                "model": "child-provider-model",
                "provider_settings": {},
                "tool_choice": None,
                "response_format": None,
                "model_settings": {},
            },
        ).json()
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "No filesystem child profile",
                name="worker",
                description="Works without filesystem tools.",
                capability_overrides=[
                    {
                        "type": "model",
                        "mode": "replace",
                        "block_id": child_model_block["id"],
                    },
                    {
                        "type": "subagent",
                        "mode": "disabled",
                        "block_id": "",
                    },
                ],
            ),
        ).json()
        disabled_delegation_override = client.put(
            f"/api/subagents/{subagent['id']}",
            json=subagent_payload(
                subagent["component_name"],
                name=subagent["name"],
                description=subagent["description"],
                capability_overrides=subagent["settings"]["capability_overrides"],
                subagents=[{"subagent_id": subagent["id"]}],
            ),
        )
        assert disabled_delegation_override.status_code == 200, (
            disabled_delegation_override.text
        )
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "No filesystem delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{parent['id']}",
            json={
                "name": parent["name"],
                "capability_refs": [
                    *parent["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": parent["name"],
                "messages": [{"role": "user", "content": "Delegate this."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "parent completed"
    )
    assert ParentModel.bound_tool_names == ["read_file", "task"]
    assert ChildModel.bound_tool_names == ["read_file"]
    assert [
        (message.type, message.text)
        for message in ChildModel.seen_messages[0]
        if message.type != "system"
    ] == [
        ("human", "Delegate this."),
        ("human", "Complete the isolated task."),
    ]


def test_unconfigured_filesystem_keeps_skill_reads_agent_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_dir = tmp_path / "data" / "resources" / "skills"
    for name, marker in (("alpha", "ALPHA ONLY"), ("beta", "BETA ONLY")):
        folder = skills_dir / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Use {name}.\n---\n{marker}\n",
            encoding="utf-8",
        )

    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "task",
                    "args": {
                        "description": "Inspect the child Skill boundary.",
                        "subagent_type": "beta_worker",
                    },
                    "id": "call-fallback-child",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/skills/alpha/SKILL.md"},
                    "id": "call-parent-own-skill",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/skills/beta/SKILL.md"},
                    "id": "call-parent-foreign-skill",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="default workspace boundary completed"),
        ]
    )
    child_model = ChildModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/skills/beta/SKILL.md"},
                    "id": "call-child-own-skill",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/skills/alpha/SKILL.md"},
                    "id": "call-child-foreign-skill",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="child boundary checked"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: (
                child_model if block["name"] == "Fallback child model" else parent_model
            ),
        )
        primary = create_primary(client, include_filesystem=False)
        child_model_response = client.post(
            "/api/blocks/model",
            json={
                "name": "Fallback child model",
                "provider": "openai",
                "base_url": "https://provider.example/v1",
                "credential": "child-provider-secret",
                "model": "child-provider-model",
                "provider_settings": {},
                "tool_choice": None,
                "response_format": None,
                "model_settings": {},
            },
        )
        assert child_model_response.status_code == 200, child_model_response.text
        child_model_block = child_model_response.json()
        alpha_response = client.post(
            "/api/blocks/skill",
            json={"name": "Alpha fallback Skill", "skills": ["alpha"]},
        )
        assert alpha_response.status_code == 200, alpha_response.text
        alpha = alpha_response.json()
        beta_response = client.post(
            "/api/blocks/skill",
            json={"name": "Beta fallback Skill", "skills": ["beta"]},
        )
        assert beta_response.status_code == 200, beta_response.text
        beta = beta_response.json()
        subagent_response = client.post(
            "/api/subagents",
            json=subagent_payload(
                "Beta fallback profile",
                name="beta_worker",
                description="Checks the beta-only Skill boundary.",
                capability_overrides=[
                    {
                        "type": "model",
                        "mode": "replace",
                        "block_id": child_model_block["id"],
                    },
                    {
                        "type": "skill",
                        "mode": "replace",
                        "block_id": beta["id"],
                    },
                ],
            ),
        )
        assert subagent_response.status_code == 200, subagent_response.text
        subagent = subagent_response.json()
        delegation_response = client.post(
            "/api/blocks/subagent",
            json={"name": "Fallback delegation"},
        )
        assert delegation_response.status_code == 200, delegation_response.text
        delegation = delegation_response.json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "skill", "block_id": alpha["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Check Skill isolation."}],
            },
        )

    assert response.status_code == 200, response.text
    assert ParentModel.bound_tool_names == ["read_file", "task"]
    assert ChildModel.bound_tool_names == ["read_file"]

    parent_messages = ParentModel.seen_messages[-1]
    child_messages = ChildModel.seen_messages[-1]
    parent_results = {
        message.tool_call_id: str(message.content)
        for message in parent_messages
        if isinstance(message, ToolMessage)
    }
    child_results = {
        message.tool_call_id: str(message.content)
        for message in child_messages
        if isinstance(message, ToolMessage)
    }
    assert "ALPHA ONLY" in parent_results["call-parent-own-skill"]
    assert "not found" in parent_results["call-parent-foreign-skill"].lower()
    assert "BETA ONLY" in child_results["call-child-own-skill"]
    assert "not found" in child_results["call-child-foreign-skill"].lower()

    parent_system = "\n".join(
        message.text for message in ParentModel.seen_messages[0]
        if message.type == "system"
    )
    child_system = "\n".join(
        message.text for message in ChildModel.seen_messages[0]
        if message.type == "system"
    )
    assert "alpha" in parent_system and "beta" not in parent_system
    assert "beta" in child_system and "alpha" not in child_system
