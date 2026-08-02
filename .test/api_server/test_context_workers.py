from __future__ import annotations

from .support import *


def _create_block(client, block_type: str, payload: dict) -> dict:
    response = client.post(f"/api/blocks/{block_type}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _model_payload(name: str) -> dict:
    return {
        "name": name,
        "provider": "openai",
        "base_url": "https://provider.example/v1",
        "credential": f"{name}-secret",
        "model": name,
        "provider_settings": {},
        "tool_choice": None,
        "response_format": None,
        "model_settings": {},
    }


def test_context_workers_receive_frozen_client_context_and_run_in_one_tool_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    class AlphaModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    class BetaModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_worker",
                        "args": {"worker": "alpha", "task": "Analyze alpha."},
                        "id": "call-alpha",
                        "type": "tool_call",
                    },
                    {
                        "name": "run_worker",
                        "args": {"worker": "beta", "task": "Analyze beta."},
                        "id": "call-beta",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="coordinator completed"),
        ]
    )
    alpha_model = AlphaModel(responses=[AIMessage(content="alpha result")])
    beta_model = BetaModel(responses=[AIMessage(content="beta result")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, _http_clients: {
                "Alpha model": alpha_model,
                "Beta model": beta_model,
            }.get(block["name"], parent_model),
        )
        primary = create_primary(client, include_filesystem=False)
        alpha_block = _create_block(client, "model", _model_payload("Alpha model"))
        beta_block = _create_block(client, "model", _model_payload("Beta model"))
        primary_preset = _create_block(
            client,
            "prompt-preset",
            {
                "name": "Coordinator preset",
                "tag_replacements": [
                    {"tag": "|||mode|||", "replacement": "PRIMARY"}
                ],
                "startup_messages": [
                    {
                        "role": "user",
                        "content_template": "Workers:\n{available_workers}",
                    }
                ],
            },
        )
        worker_presets = {}
        for name in ("alpha", "beta"):
            worker_presets[name] = _create_block(
                client,
                "prompt-preset",
                {
                    "name": f"{name} preset",
                    "tag_replacements": [
                        {"tag": "|||mode|||", "replacement": name.upper()}
                    ],
                    "startup_messages": [
                        {"role": "user", "content_template": "Task: {task}"},
                        {"role": "assistant", "content_template": "Understood."},
                        {"role": "user", "content_template": "Begin."},
                    ],
                },
            )
        profiles = {}
        for name, model_block in (("alpha", alpha_block), ("beta", beta_block)):
            response = client.post(
                "/api/worker-profiles",
                json={
                    "name": f"{name} profile",
                    "include_client_messages": True,
                    "capability_overrides": [
                        {
                            "type": "model",
                            "mode": "replace",
                            "block_id": model_block["id"],
                        },
                        {
                            "type": "prompt-preset",
                            "mode": "replace",
                            "block_id": worker_presets[name]["id"],
                        },
                    ],
                },
            )
            assert response.status_code == 200, response.text
            profiles[name] = response.json()
        delegation = _create_block(
            client,
            "worker-delegation",
            {"name": "Context delegation", "max_parallel_workers": 2},
        )
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "prompt-preset", "block_id": primary_preset["id"]},
                    {"type": "worker-delegation", "block_id": delegation["id"]},
                ],
                "subagents": [],
                "workers": [
                    {
                        "name": name,
                        "description": f"The {name} worker.",
                        "worker_profile_id": profiles[name]["id"],
                    }
                    for name in ("alpha", "beta")
                ],
            },
        )
        assert updated.status_code == 200, updated.text

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "user", "content": "Shared context |||mode|||"}
                ],
            },
        )
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "coordinator completed"
    )
    assert ParentModel.bound_tool_names == ["run_worker"]
    assert AlphaModel.bound_tool_names == ["run_worker"]
    assert BetaModel.bound_tool_names == ["run_worker"]
    assert "Shared context ALPHA" in [message.text for message in AlphaModel.seen_messages[0]]
    assert "Task: Analyze alpha." in [
        message.text for message in AlphaModel.seen_messages[0]
    ]
    assert "Shared context BETA" in [message.text for message in BetaModel.seen_messages[0]]
    tool_messages = [
        message
        for message in ParentModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert {message.tool_call_id: message.text for message in tool_messages} == {
        "call-alpha": "alpha result",
        "call-beta": "beta result",
    }
    timeline = session["runs"][0]["timeline"]
    model_requests = [
        event["data"] for event in timeline if event["kind"] == "model_request"
    ]
    assert len(model_requests) == 4
    assert {
        (event["agent_type"], event["agent_name"], event["tool_call_id"])
        for event in model_requests
    } == {
        ("primary", primary["name"], ""),
        ("context_worker", "alpha", "call-alpha"),
        ("context_worker", "beta", "call-beta"),
    }
    agent_inputs = [
        event["data"] for event in timeline if event["kind"] == "agent_input"
    ]
    assert len(agent_inputs) == 3
    assert {event["agent_type"] for event in agent_inputs} == {
        "primary",
        "context_worker",
    }
    model_responses = [
        event["data"] for event in timeline if event["kind"] == "model_response"
    ]
    assert len(model_responses) == 4
    assert {event["agent_name"] for event in model_responses} == {
        primary["name"],
        "alpha",
        "beta",
    }
    persisted_payloads = [event["data"] for event in timeline]
    assert all(
        {"messages", "arguments", "output", "message", "content_blocks"}.isdisjoint(
            payload
        )
        for payload in persisted_payloads
    )
