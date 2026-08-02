from __future__ import annotations

from .support import *
from agent_shell.runtime.capabilities import deepagents as deepagents_capability

def test_subagent_runs_without_project_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        bound_tool_names: ClassVar[list[str]] = []

    class ChildModel(ToolCallingFakeModel):
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
        override = client.post(
            "/api/subagent-overrides",
            json={
                "name": "No filesystem child model",
                "capability_overrides": [
                    {
                        "type": "model",
                        "mode": "replace",
                        "block_id": child_model_block["id"],
                    }
                ],
            },
        ).json()
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
                "subagents": [
                    {
                        "name": "worker",
                        "description": "Works without filesystem tools.",
                        "subagent_override_id": override["id"],
                    }
                ],
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
    assert ParentModel.bound_tool_names == ["task"]
    assert ChildModel.bound_tool_names == []


def test_skill_fallback_is_consumer_local_and_read_only_for_subagent(
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
            AIMessage(content="fallback boundary completed"),
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
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/temp/parent-state.txt"},
                    "id": "call-child-parent-state",
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
        override_response = client.post(
            "/api/subagent-overrides",
            json={
                "name": "Beta fallback override",
                "capability_overrides": [
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
            },
        )
        assert override_response.status_code == 200, override_response.text
        override = override_response.json()
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
                "subagents": [{
                    "name": "beta_worker",
                    "description": "Checks the beta-only Skill boundary.",
                    "subagent_override_id": override["id"],
                }],
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
    assert "not found" in child_results["call-child-parent-state"].lower()

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


def test_shared_filesystem_keeps_skill_namespace_isolated_between_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "seed" / "shared.txt"
    source.parent.mkdir()
    source.write_text("SHARED REQUEST FILE", encoding="utf-8")
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
                        "write_file",
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
    assert ParentModel.bound_tool_names == ["read_file", "task"]
    assert ChildAModel.bound_tool_names == ["read_file"]
    assert ChildBModel.bound_tool_names == ["read_file"]

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
    assert "BETA ONLY" in beta_results["call-beta-own"]
    assert "not found" in beta_results["call-beta-foreign"].lower()
    assert "SHARED REQUEST FILE" in beta_results["call-beta-shared"]
    assert "GAMMA ONLY" in gamma_results["call-gamma-own"]
    assert "not found" in gamma_results["call-gamma-foreign"].lower()
    assert "SHARED REQUEST FILE" in gamma_results["call-gamma-shared"]


def test_selected_subagent_applies_effective_overrides_and_returns_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Solve the delegated check.",
                            "subagent_type": "worker",
                        },
                        "id": "call-subagent",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="parent completed"),
        ]
    )
    child_model = ChildModel(responses=[AIMessage(content="child result")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: (
                child_model if block["name"] == "Child model" else parent_model
            ),
        )
        parent = create_primary(client)
        child_model_block = client.post(
            "/api/blocks/model",
            json={
                "name": "Child model",
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
        override_prompt = client.post(
            "/api/blocks/system-prompt",
            json={
                "name": "Override child prompt",
                "system_prompt": "OVERRIDE CHILD PROMPT",
            },
        ).json()
        override_response = client.post(
            "/api/subagent-overrides",
            json={
                "name": "Child runtime override",
                "capability_overrides": [
                    {
                        "type": "model",
                        "mode": "replace",
                        "block_id": child_model_block["id"],
                    },
                    {
                        "type": "system-prompt",
                        "mode": "replace",
                        "block_id": override_prompt["id"],
                    },
                ],
            },
        )
        assert override_response.status_code == 200, override_response.text
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Runtime delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{parent['id']}",
            json={
                "name": parent["name"],
                "capability_refs": [
                    *parent["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "worker",
                        "description": "Handles the delegated check.",
                        "subagent_override_id": override_response.json()["id"],
                    }
                ],
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
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "parent completed"
    )
    assert ParentModel.bound_tool_names == ["read_file", "task"]
    assert ChildModel.bound_tool_names == ["read_file"]
    child_system = next(
        message for message in ChildModel.seen_messages[0] if message.type == "system"
    )
    assert child_system.text == "OVERRIDE CHILD PROMPT"
    assert "Filesystem Tools" not in child_system.text
    assert all(
        "task tool to launch short-lived subagents" not in message.text
        for message in ParentModel.seen_messages[0]
        if message.type == "system"
    )
    child_human = next(
        message for message in ChildModel.seen_messages[0] if message.type == "human"
    )
    assert child_human.text == "Solve the delegated check."
    task_result = next(
        message
        for message in ParentModel.seen_messages[1]
        if isinstance(message, ToolMessage) and message.name == "task"
    )
    assert task_result.content == "child result"
    subagent_events = [
        item
        for item in session["runs"][0]["timeline"]
        if item["kind"] == "subagent"
    ]
    assert [
        (
            item["data"]["phase"],
            item["data"]["subagent_name"],
            item["data"]["tool_call_id"],
            item["data"]["status"],
        )
        for item in subagent_events
    ] == [
        ("start", "worker", "call-subagent", "started"),
        ("end", "worker", "call-subagent", "completed"),
    ]
    assert subagent_events[0]["data"]["namespace"] != "root"
    assert (
        subagent_events[0]["data"]["namespace"]
        == subagent_events[1]["data"]["namespace"]
    )

def test_subagent_inherits_current_primary_without_saved_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Run with the current Primary profile.",
                            "subagent_type": "self_worker",
                        },
                        "id": "call-self-subagent",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="parent received self result"),
        ]
    )
    child_model = ChildModel(responses=[AIMessage(content="self child result")])
    models = iter([parent_model, child_model])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        prompt = client.post(
            "/api/blocks/system-prompt",
            json={
                "name": "Self inherited prompt",
                "system_prompt": "SELF INHERITED PROMPT",
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Self delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "system-prompt", "block_id": prompt["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "self_worker",
                        "description": "Uses the current Primary without an override profile.",
                        "subagent_override_id": "",
                    }
                ],
            },
        )
        assert updated.status_code == 200, updated.text
        assert client.get("/api/subagent-overrides").json() == []

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Delegate to self."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "parent received self result"
    )
    assert ParentModel.bound_tool_names == ["read_file", "task"]
    assert ChildModel.bound_tool_names == ["read_file"]
    child_system = next(
        message for message in ChildModel.seen_messages[0] if message.type == "system"
    )
    assert child_system.text == "SELF INHERITED PROMPT"
    assert "Filesystem Tools" not in child_system.text

def test_subagent_shares_primary_request_files_without_reloading_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "seed" / "note.txt"
    source.parent.mkdir()
    source.write_text("shared source content", encoding="utf-8")
    source_reads: list[Path] = []
    original_file_data_from_path = deepagents_capability._file_data_from_path

    def tracked_file_data_from_path(path: Path, create_file_data):
        if path == source:
            source_reads.append(path)
        return original_file_data_from_path(path, create_file_data)

    monkeypatch.setattr(
        deepagents_capability, "_file_data_from_path", tracked_file_data_from_path
    )

    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Read the shared source and create a draft.",
                            "subagent_type": "workspace_worker",
                        },
                        "id": "call-shared-worker",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/temp/child.txt"},
                        "id": "call-read-child-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="shared workspace completed"),
        ]
    )
    child_model = ChildModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/input/note.txt"},
                        "id": "call-child-read-source",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/temp/child.txt",
                            "content": "created by child",
                        },
                        "id": "call-child-write",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="child workspace updated"),
        ]
    )
    models = iter([parent_model, child_model])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, *_args: next(models),
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Shared request workspace",
                "virtual_files": [
                    {
                        "virtual_path": "/input/note.txt",
                        "source_path": str(source),
                    }
                ],
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Shared workspace delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
                    ),
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "workspace_worker",
                        "description": "Uses the current Primary workspace.",
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
                "messages": [{"role": "user", "content": "Use the shared workspace."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "shared workspace completed"
    )
    assert source_reads == [source]
    child_read_result = next(
        message
        for message in ChildModel.seen_messages[1]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "shared source content" in str(child_read_result.content)
    parent_read_result = next(
        message
        for message in ParentModel.seen_messages[2]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "created by child" in str(parent_read_result.content)

def test_new_request_resets_state_backend_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/temp/generated.txt",
                            "content": "first request only",
                        },
                        "id": "call-write-request-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="first request completed"),
        ]
    )
    reader = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/temp/generated.txt"},
                        "id": "call-read-request-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="second request completed"),
        ]
    )
    models = iter([writer, reader])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Ephemeral request workspace"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": replace_capability_reference(
                    primary, "filesystem", filesystem["id"]
                ),
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        first = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Create a temporary file."}],
            },
        )
        second = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Read the temporary file."}],
            },
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    read_result = next(
        message
        for message in ToolCallingFakeModel.seen_messages[-1]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "not found" in str(read_result.content).lower()

def test_unknown_subagent_capability_returns_stable_error_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        parent = create_primary(client)
        override = client.post(
            "/api/subagent-overrides",
            json={"name": "Stale child override", "capability_overrides": []},
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Stale delegation"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{parent['id']}",
            json={
                "name": parent["name"],
                "capability_refs": [
                    *parent["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {
                        "name": "stale_worker",
                        "description": "Exercises stale Subagent capability data.",
                        "subagent_override_id": override["id"],
                    }
                ],
            },
        )
        assert updated.status_code == 200, updated.text

        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM subagent_overrides WHERE id = ?", (override["id"],)
            ).fetchone()
            payload = json.loads(row[0])
            payload["capability_overrides"].append(
                {
                    "type": "context-assembler",
                    "mode": "disabled",
                    "block_id": "",
                }
            )
            connection.execute(
                "UPDATE subagent_overrides SET payload = ? WHERE id = ?",
                (json.dumps(payload), override["id"]),
            )
            connection.commit()

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": parent["name"],
                "messages": [{"role": "user", "content": "run stale child"}],
            },
        )
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="run stale child"),
        ).json()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assembly.subagent_override_invalid"
    assert "context-assembler" in response.json()["error"]["message"]
    assert len(history["items"]) == 1
    assert "assembly.subagent_override_invalid" in history["items"][0]["summary"]
