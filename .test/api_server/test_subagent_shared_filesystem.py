from __future__ import annotations

from .support import *


def test_shared_filesystem_merges_parallel_children_and_scopes_skill_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "seed" / "shared.txt"
    source.parent.mkdir()
    source.write_text("SHARED REQUEST FILE", encoding="utf-8")
    mapped = tmp_path / "mapped"
    mapped.mkdir()
    (mapped / "host.txt").write_text("SHARED MAPPED FILE", encoding="utf-8")
    skills_dir = tmp_path / "data" / "resources" / "skills"
    for name, marker in (
        ("alpha", "ALPHA ONLY"),
        ("beta", "BETA ONLY"),
        ("gamma", "GAMMA ONLY"),
    ):
        folder = skills_dir / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Use {name}.\n---\n{marker}\n",
            encoding="utf-8",
        )

    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    class ChildAModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    class ChildBModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    def read_calls(*calls: tuple[str, str]) -> list[AIMessage]:
        return [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": path},
                    "id": call_id,
                    "type": "tool_call",
                }],
            )
            for call_id, path in calls
        ]

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Check beta workspace.",
                            "subagent_type": "beta_worker",
                        },
                        "id": "call-shared-beta",
                        "type": "tool_call",
                    },
                    {
                        "name": "task",
                        "args": {
                            "description": "Check gamma workspace.",
                            "subagent_type": "gamma_worker",
                        },
                        "id": "call-shared-gamma",
                        "type": "tool_call",
                    },
                ],
            ),
            *read_calls(
                ("call-parent-alpha", "/skills/alpha/SKILL.md"),
                ("call-parent-beta", "/skills/beta/SKILL.md"),
                ("call-parent-shared", "/input/shared.txt"),
                ("call-parent-beta-output", "/temp/beta.txt"),
                ("call-parent-gamma-output", "/temp/gamma.txt"),
            ),
            AIMessage(content="shared workspace and isolated Skills completed"),
        ]
    )
    child_a_model = ChildAModel(
        responses=[
            *read_calls(
                ("call-beta-own", "/skills/beta/SKILL.md"),
                ("call-beta-foreign", "/skills/gamma/SKILL.md"),
                ("call-beta-shared", "/input/shared.txt"),
                ("call-beta-mapped", "/mapped/host.txt"),
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "write_file",
                    "args": {
                        "file_path": "/temp/beta.txt",
                        "content": "created by beta child",
                    },
                    "id": "call-beta-write",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="beta worker completed"),
        ]
    )
    child_b_model = ChildBModel(
        responses=[
            *read_calls(
                ("call-gamma-own", "/skills/gamma/SKILL.md"),
                ("call-gamma-foreign", "/skills/beta/SKILL.md"),
                ("call-gamma-shared", "/input/shared.txt"),
                ("call-gamma-mapped", "/mapped/host.txt"),
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "write_file",
                    "args": {
                        "file_path": "/temp/gamma.txt",
                        "content": "created by gamma child",
                    },
                    "id": "call-gamma-write",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="gamma worker completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        def create_child_model(name: str) -> dict:
            response = client.post(
                "/api/blocks/model",
                json={
                    "name": name,
                    "provider": "openai",
                    "base_url": "https://provider.example/v1",
                    "credential": f"{name}-secret",
                    "model": f"{name}-model",
                    "provider_settings": {},
                    "tool_choice": None,
                    "response_format": None,
                    "model_settings": {},
                },
            )
            assert response.status_code == 200, response.text
            return response.json()

        models = {
            "Shared child beta model": child_a_model,
            "Shared child gamma model": child_b_model,
        }
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: models.get(block["name"], parent_model),
        )
        primary = create_primary(client)
        filesystem_response = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Shared Skill boundary filesystem",
                "tool_configs": {
                    name: {"visible": False}
                    for name in (
                        "ls",
                        "edit_file",
                        "delete",
                        "glob",
                        "grep",
                        "execute",
                    )
                },
                "virtual_files": [{
                    "virtual_path": "/input/shared.txt",
                    "source_path": str(source),
                }],
                "mapped_directories": [{
                    "virtual_path": "/mapped/",
                    "local_path": str(mapped),
                }],
            },
        )
        assert filesystem_response.status_code == 200, filesystem_response.text
        filesystem = filesystem_response.json()

        skill_blocks: dict[str, dict] = {}
        for name in ("alpha", "beta", "gamma"):
            skill_response = client.post(
                "/api/blocks/skill",
                json={"name": f"{name} shared Skill", "skills": [name]},
            )
            assert skill_response.status_code == 200, skill_response.text
            skill_blocks[name] = skill_response.json()
        beta_model = create_child_model("Shared child beta model")
        gamma_model = create_child_model("Shared child gamma model")

        def create_override(name: str, model: dict, skill: dict) -> dict:
            response = client.post(
                "/api/subagent-overrides",
                json={
                    "name": name,
                    "capability_overrides": [
                        {
                            "type": "model",
                            "mode": "replace",
                            "block_id": model["id"],
                        },
                        {
                            "type": "skill",
                            "mode": "replace",
                            "block_id": skill["id"],
                        },
                    ],
                },
            )
            assert response.status_code == 200, response.text
            return response.json()

        beta_override = create_override(
            "Shared beta override", beta_model, skill_blocks["beta"]
        )
        gamma_override = create_override(
            "Shared gamma override", gamma_model, skill_blocks["gamma"]
        )
        delegation_response = client.post(
            "/api/blocks/subagent",
            json={"name": "Shared Skill delegation"},
        )
        assert delegation_response.status_code == 200, delegation_response.text
        delegation = delegation_response.json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
                    ),
                    {"type": "skill", "block_id": skill_blocks["alpha"]["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "beta_worker",
                        "description": "Uses the beta Skill and shared workspace.",
                        "subagent_override_id": beta_override["id"],
                    },
                    {
                        "name": "gamma_worker",
                        "description": "Uses the gamma Skill and shared workspace.",
                        "subagent_override_id": gamma_override["id"],
                    },
                ],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Check shared files and Skills."}],
            },
        )

    assert response.status_code == 200, response.text
    assert ParentModel.bound_tool_names == ["read_file", "write_file", "task"]
    assert ChildAModel.bound_tool_names == ["read_file", "write_file"]
    assert ChildBModel.bound_tool_names == ["read_file", "write_file"]

    def results(messages: list[object]) -> dict[str, str]:
        return {
            message.tool_call_id: str(message.content)
            for message in messages
            if isinstance(message, ToolMessage)
        }

    parent_results = results(ParentModel.seen_messages[-1])
    beta_results = results(ChildAModel.seen_messages[-1])
    gamma_results = results(ChildBModel.seen_messages[-1])
    assert "ALPHA ONLY" in parent_results["call-parent-alpha"]
    assert "not found" in parent_results["call-parent-beta"].lower()
    assert "SHARED REQUEST FILE" in parent_results["call-parent-shared"]
    assert "created by beta child" in parent_results["call-parent-beta-output"]
    assert "created by gamma child" in parent_results["call-parent-gamma-output"]
    assert "BETA ONLY" in beta_results["call-beta-own"]
    assert "not found" in beta_results["call-beta-foreign"].lower()
    assert "SHARED REQUEST FILE" in beta_results["call-beta-shared"]
    assert "SHARED MAPPED FILE" in beta_results["call-beta-mapped"]
    assert "GAMMA ONLY" in gamma_results["call-gamma-own"]
    assert "not found" in gamma_results["call-gamma-foreign"].lower()
    assert "SHARED REQUEST FILE" in gamma_results["call-gamma-shared"]
    assert "SHARED MAPPED FILE" in gamma_results["call-gamma-mapped"]

    parent_system = "\n".join(
        message.text for message in ParentModel.seen_messages[0]
        if message.type == "system"
    )
    beta_system = "\n".join(
        message.text for message in ChildAModel.seen_messages[0]
        if message.type == "system"
    )
    gamma_system = "\n".join(
        message.text for message in ChildBModel.seen_messages[0]
        if message.type == "system"
    )
    assert "alpha" in parent_system and "beta" not in parent_system
    assert "beta" in beta_system and "gamma" not in beta_system
    assert "gamma" in gamma_system and "beta" not in gamma_system
