from __future__ import annotations

from .support import *


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
        parent = create_main_agent(client)
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
        subagent_response = client.post(
            "/api/subagents",
            json={
                "component_name": "Child runtime profile",
                "name": "worker",
                "description": "Handles the delegated check.",
                "settings": {
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
                    "subagents": [],
                },
            },
        )
        assert subagent_response.status_code == 200, subagent_response.text
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Runtime delegation"},
        ).json()
        updated = client.put(
            f"/api/main-agents/{parent['id']}",
            json={
                "name": parent["name"],
                "capability_refs": [
                    *parent["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [
                    {"subagent_id": subagent_response.json()["id"]}
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
    assert [
        message.text
        for message in ChildModel.seen_messages[0]
        if message.type == "human"
    ] == ["Solve the delegated check."]
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
    agent_inputs = [
        item["data"]
        for item in session["runs"][0]["timeline"]
        if item["kind"] == "agent_input"
    ]
    assert [item["agent_type"] for item in agent_inputs] == [
        "main_agent",
        "subagent",
    ]
    root_invocation, child_invocation = agent_inputs
    assert root_invocation["invocation_id"]
    assert root_invocation["parent_invocation_id"] == ""
    assert root_invocation["tool_call_id"] == ""
    assert child_invocation["invocation_id"] != root_invocation["invocation_id"]
    assert (
        child_invocation["parent_invocation_id"]
        == root_invocation["invocation_id"]
    )
    assert child_invocation["tool_call_id"] == "call-subagent"


def test_subagent_entity_can_inherit_current_main_agent_capabilities(
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
                            "description": "Run with the current Main Agent profile.",
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
        main_agent = create_main_agent(client)
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
        subagent = client.post(
            "/api/subagents",
            json={
                "component_name": "Inherited worker",
                "name": "self_worker",
                "description": "Uses the current Main Agent capabilities.",
                "settings": {"capability_overrides": [], "subagents": []},
            },
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {"type": "system-prompt", "block_id": prompt["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        assert client.get("/api/subagents").json() == [subagent]

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
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


def test_unknown_subagent_capability_returns_stable_error_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        parent = create_main_agent(client)
        subagent = client.post(
            "/api/subagents",
            json={
                "component_name": "Stale child profile",
                "name": "stale_worker",
                "description": "Exercises stale Subagent capability data.",
                "settings": {"capability_overrides": [], "subagents": []},
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Stale delegation"},
        ).json()
        updated = client.put(
            f"/api/main-agents/{parent['id']}",
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

        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM subagents WHERE id = ?", (subagent["id"],)
            ).fetchone()
            payload = json.loads(row[0])
            payload["settings"]["capability_overrides"].append(
                {
                    "type": "context-assembler",
                    "mode": "disabled",
                    "block_id": "",
                }
            )
            connection.execute(
                "UPDATE subagents SET payload = ? WHERE id = ?",
                (json.dumps(payload), subagent["id"]),
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
    assert response.json()["error"]["code"] == "assembly.subagent_invalid"
    assert "context-assembler" in response.json()["error"]["message"]
    assert len(history["items"]) == 1
    assert "assembly.subagent_invalid" in history["items"][0]["summary"]
