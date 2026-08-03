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
    recursive_description = "Continues the recursive task."

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "Recursive profile",
                name="recursive_worker",
                description=recursive_description,
            ),
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
        recursive_profile = client.put(
            f"/api/subagents/{subagent['id']}",
            json=subagent_payload(
                subagent["component_name"],
                name=subagent["name"],
                description=recursive_description,
                capability_overrides=[{
                    "type": "subagent",
                    "mode": "replace",
                    "block_id": child_delegation["id"],
                }],
                subagents=[{"subagent_id": subagent["id"]}],
            ),
        )
        assert recursive_profile.status_code == 200, recursive_profile.text
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
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
        write_automation_script(
            tmp_path,
            "append-subagent-startup",
            "async def run(ctx):\n"
            "    ctx.messages.extend(dict(message) for message in ctx.config['messages'])\n",
        )
        startup_workflow = create_hook_workflow(
            client,
            "Delegated task startup",
            subagent_before_invoke=[
                {
                    "script_id": "append-subagent-startup",
                    "config": {
                        "messages": [
                            {"role": "user", "content": "Delegated work."},
                            {
                                "role": "assistant",
                                "content": "Ready for delegated work.",
                            },
                        ]
                    },
                }
            ],
        )

        def create_subagent(
            component_name: str,
            routing_name: str,
            description: str,
            model: dict,
            hook_workflow: dict | None = None,
        ) -> dict:
            capability_overrides = [{
                "type": "model",
                "mode": "replace",
                "block_id": model["id"],
            }]
            payload = subagent_payload(
                component_name,
                name=routing_name,
                description=description,
                capability_overrides=capability_overrides,
            )
            if hook_workflow is not None:
                payload["settings"]["automation"] = {
                    "hook_workflow": {
                        "mode": "replace",
                        "workflow_id": hook_workflow["id"],
                    },
                    "lifecycle_workflow": {
                        "mode": "inherit",
                        "workflow_id": "",
                    },
                }
            response = client.post(
                "/api/subagents",
                json=payload,
            )
            assert response.status_code == 200, response.text
            return response.json()

        prompt_subagent = create_subagent(
            "Override prompt child",
            "override_worker",
            "Uses child-only startup automation.",
            override_model,
            startup_workflow,
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
                "subagents": [{"subagent_id": prompt_subagent["id"]}],
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
        ("human", "Delegated work."),
        ("ai", "Ready for delegated work."),
        ("human", "Run the override prompt."),
    ]
