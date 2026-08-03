from __future__ import annotations

from .support import *


def test_named_subagent_can_reference_itself_with_matching_task_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        tool_signatures: ClassVar[list[tuple[str, str, dict]]] = []

        def bind_tools(self, tools, **kwargs):
            type(self).tool_signatures = [
                (tool.name, tool.description, tool.args_schema.model_json_schema())
                for tool in tools
            ]
            return super().bind_tools(tools, **kwargs)

    class ChildModel(ParentModel):
        seen_messages: ClassVar[list[list[object]]] = []
        tool_signatures: ClassVar[list[tuple[str, str, dict]]] = []

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "task",
                    "args": {
                        "description": "Run the recursive worker.",
                        "subagent_type": "recursive_worker",
                    },
                    "id": "call-recursive-root",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="recursive parent completed"),
        ]
    )
    child_model = ChildModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "task",
                    "args": {
                        "description": "Run one nested step.",
                        "subagent_type": "recursive_worker",
                    },
                    "id": "call-recursive-child",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="nested result"),
            AIMessage(content="outer child result"),
        ]
    )
    models = iter([parent_model, child_model])
    binding = {
        "name": "recursive_worker",
        "description": "Continues the recursive task.",
    }

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        override = client.post(
            "/api/subagent-overrides",
            json={"name": "Recursive profile", "capability_overrides": []},
        ).json()
        custom_task_description = (
            "Delegate one complete task to this catalog:\n"
            "{available_agents}\n"
            "Return one final report."
        )
        child_task_description = (
            "Delegate recursively with this child catalog:\n"
            "{available_agents}"
        )
        delegation = client.post(
            "/api/blocks/subagent",
            json={
                "name": "Recursive delegation",
                "task_description_override": custom_task_description,
            },
        ).json()
        child_delegation = client.post(
            "/api/blocks/subagent",
            json={
                "name": "Child recursive delegation",
                "task_description_override": child_task_description,
            },
        ).json()
        recursive_override = client.put(
            f"/api/subagent-overrides/{override['id']}",
            json={
                "name": override["name"],
                "capability_overrides": [{
                    "type": "subagent",
                    "mode": "replace",
                    "block_id": child_delegation["id"],
                }],
                "subagents": [{
                    **binding,
                    "subagent_override_id": override["id"],
                }],
            },
        )
        assert recursive_override.status_code == 200, recursive_override.text
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{
                    **binding,
                    "subagent_override_id": override["id"],
                }],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Run recursion."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "recursive parent completed"
    )
    parent_task = next(item for item in ParentModel.tool_signatures if item[0] == "task")
    child_task = next(item for item in ChildModel.tool_signatures if item[0] == "task")
    assert parent_task[1] == custom_task_description.format(
        available_agents="- recursive_worker: Continues the recursive task."
    )
    assert child_task[1] == child_task_description.format(
        available_agents="- recursive_worker: Continues the recursive task."
    )
    assert len(ChildModel.seen_messages) == 3


def test_subagent_prompt_override_builds_from_frozen_client_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []

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
                        "description": "Run the override prompt.",
                        "subagent_type": "override_worker",
                    },
                    "id": "call-override-prompt",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="parent completed"),
        ]
    )
    child_model = ChildModel(
        responses=[AIMessage(content="override child completed")]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: (
                child_model if block["name"] == "Override child model" else parent_model
            ),
        )
        primary = create_primary(client, include_filesystem=False)

        def create_model(name: str) -> dict:
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

        override_model = create_model("Override child model")
        override_preset_response = client.post(
            "/api/blocks/prompt-preset",
            json={
                "name": "Delegated task startup",
                "tag_replacements": [],
                "startup_messages": [
                    {
                        "role": "user",
                        "content_template": "Delegated: {task}",
                    },
                    {
                        "role": "assistant",
                        "content_template": "Ready for delegated work.",
                    },
                ],
            },
        )
        assert override_preset_response.status_code == 200, (
            override_preset_response.text
        )
        override_preset = override_preset_response.json()

        def create_override(
            name: str, model: dict, prompt_preset: dict | None = None
        ) -> dict:
            capability_overrides = [{
                "type": "model",
                "mode": "replace",
                "block_id": model["id"],
            }]
            if prompt_preset is not None:
                capability_overrides.append({
                    "type": "prompt-preset",
                    "mode": "replace",
                    "block_id": prompt_preset["id"],
                })
            response = client.post(
                "/api/subagent-overrides",
                json={
                    "name": name,
                    "capability_overrides": capability_overrides,
                },
            )
            assert response.status_code == 200, response.text
            return response.json()

        prompt_override = create_override(
            "Override prompt child", override_model, override_preset
        )
        delegation_response = client.post(
            "/api/blocks/subagent",
            json={
                "name": "Prompt construction delegation",
                "task_description_override": (
                    "Run a fully specified task with this catalog:\n"
                    "{available_agents}"
                ),
            },
        )
        assert delegation_response.status_code == 200, delegation_response.text
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {
                        "type": "subagent",
                        "block_id": delegation_response.json()["id"],
                    },
                ],
                "subagents": [
                    {
                        "name": "override_worker",
                        "description": "Uses a child-only Prompt Preset.",
                        "subagent_override_id": prompt_override["id"],
                    },
                ],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "system", "content": "CLIENT SYSTEM"},
                    {"role": "user", "content": "Earlier request"},
                    {"role": "assistant", "content": "Earlier response"},
                    {"role": "user", "content": "Current request"},
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "parent completed"
    )
    assert "task" not in ChildModel.bound_tool_names
    assert ParentModel.bound_tool_descriptions["task"].startswith(
        "Run a fully specified task with this catalog:"
    )

    def messages_from_client_prefix(messages: list[object]) -> list[tuple[str, str]]:
        pairs = [(message.type, message.text) for message in messages]
        start = pairs.index(("system", "CLIENT SYSTEM"))
        return pairs[start:]

    assert messages_from_client_prefix(ChildModel.seen_messages[0]) == [
        ("system", "CLIENT SYSTEM"),
        ("human", "Earlier request"),
        ("ai", "Earlier response"),
        ("human", "Current request"),
        ("human", "Delegated: Run the override prompt."),
        ("ai", "Ready for delegated work."),
        ("human", "Run the override prompt."),
    ]
