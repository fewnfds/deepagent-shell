from __future__ import annotations

from .support import *


def test_subagent_prompt_override_uses_native_delegation(
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
        main_agent = create_main_agent(client, include_filesystem=False)

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
        def create_subagent(
            component_name: str,
            routing_name: str,
            description: str,
            model: dict,
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
            response = client.post(
                "/api/subagents",
                json=payload,
            )
            assert response.status_code == 200, response.text
            return response.json()

        prompt_subagent = create_subagent(
            "Override prompt child",
            "override_worker",
            "Uses the delegated task as its invocation input.",
            override_model,
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
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
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
                "model": main_agent["name"],
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

    child_messages = [
        (message.type, message.text) for message in ChildModel.seen_messages[0]
    ]
    assert ("system", "CLIENT SYSTEM") not in child_messages
    assert ("human", "Earlier request") not in child_messages
    assert ("ai", "Earlier response") not in child_messages
    assert ("human", "Current request") not in child_messages
    assert child_messages[-1] == ("human", "Run the override prompt.")
