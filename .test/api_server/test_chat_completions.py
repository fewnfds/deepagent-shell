from __future__ import annotations

import asyncio

from agent_shell.api import api_server

from .support import *


def test_models_publish_only_primary_agents_and_each_runs_the_minimal_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)

        models = client.get("/v1/models")
        test_reply = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hello"}]},
        )
        primary_reply = client.post(
            "/v1/chat/completions",
            json={"model": primary["name"], "messages": [{"role": "user", "content": "run"}]},
        )
        internal_uuid_reply = client.post(
            "/v1/chat/completions",
            json={"model": primary["id"], "messages": [{"role": "user", "content": "run"}]},
        )

    assert models.status_code == 200
    assert [item["id"] for item in models.json()["data"]] == [primary["name"]]
    assert test_reply.status_code == 404
    assert test_reply.json()["error"]["code"] == "model_not_found"
    assert internal_uuid_reply.status_code == 404
    assert internal_uuid_reply.json()["error"]["code"] == "model_not_found"
    assert primary_reply.status_code == 200, primary_reply.text
    assert primary_reply.json()["choices"][0]["message"] == {
        "role": "assistant",
        "content": "runtime reply",
    }


def test_primary_without_plugins_does_not_receive_client_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = RecordingFakeListChatModel(responses=["no relay"])
    RecordingFakeListChatModel.seen_messages = []
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client, include_filesystem=False)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "system", "content": "CLIENT SYSTEM"},
                    {"role": "user", "content": "CLIENT USER"},
                    {"role": "assistant", "content": "CLIENT ASSISTANT"},
                ],
            },
        )

    assert response.status_code == 200, response.text
    visible_text = {
        message.text
        for message in RecordingFakeListChatModel.seen_messages[0]
    }
    assert visible_text.isdisjoint(
        {"CLIENT SYSTEM", "CLIENT USER", "CLIENT ASSISTANT"}
    )


def test_primary_runtime_returns_stable_input_message_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = (
        (None, "input_messages_required"),
        ([], "input_messages_required"),
        (
            [{"role": "user", "content": "item"} for _ in range(1001)],
            "input_messages_too_many",
        ),
        (["not-an-object"], "input_message_invalid"),
        ([{"role": "tool", "content": "unsupported"}], "input_message_role_unsupported"),
        ([{"role": "user", "content": ["not", "text"]}], "input_content_part_invalid"),
        ([{"role": "user", "content": "named", "name": ""}], "input_message_name_invalid"),
    )

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        responses = [
            client.post(
                "/v1/chat/completions",
                json={"model": primary["name"], "messages": messages},
            )
            for messages, _expected in cases
        ]

    assert [response.status_code for response in responses] == [422] * len(cases)
    assert [response.json()["error"]["code"] for response in responses] == [
        expected for _messages, expected in cases
    ]


def test_chat_completion_body_limit_rejects_before_agent_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        monkeypatch.setattr(api_server, "MAX_CHAT_COMPLETION_BODY_BYTES", 128)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "x" * 256}],
            },
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "input_body_too_large"


def test_bounded_body_reader_stops_when_the_next_chunk_exceeds_the_limit() -> None:
    calls = 0

    async def receive() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "type": "http.request",
                "body": b"a" * 80,
                "more_body": True,
            }
        if calls == 2:
            return {
                "type": "http.request",
                "body": b"b" * 80,
                "more_body": True,
            }
        raise AssertionError("the oversized request body was read past the limit")

    async def run() -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/v1/chat/completions",
                "headers": [],
            },
            receive,
        )
        with pytest.raises(api_server._BodyTooLarge):
            await api_server._read_bounded_body(request, 128)

    asyncio.run(run())
    assert calls == 2


def test_initial_message_limit_is_configurable_and_rejects_before_agent_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        initial = client.get("/api/api-server")
        saved = client.put(
            "/api/api-server",
            json={
                "api_key": {"operation": "keep"},
                "max_initial_messages": 2,
            },
        )
        too_small = client.put(
            "/api/api-server",
            json={
                "api_key": {"operation": "keep"},
                "max_initial_messages": 0,
            },
        )
        too_large = client.put(
            "/api/api-server",
            json={
                "api_key": {"operation": "keep"},
                "max_initial_messages": 10_001,
            },
        )
        accepted = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "user", "content": "accepted first"},
                    {"role": "user", "content": "accepted second"},
                ],
            },
        )

        def fail_start(*_args, **_kwargs):
            raise AssertionError("an oversized request must not enter the Agent")

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_agent",
            fail_start,
        )
        rejected = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "user", "content": "oversized first"},
                    {"role": "assistant", "content": "oversized second"},
                    {"role": "user", "content": "oversized third"},
                ],
            },
        )
        rejected_sessions = client.get(
            "/api/agent-sessions", params={"query": "oversized third"}
        ).json()
        rejected_history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="oversized third"),
        ).json()

    with make_client(tmp_path, monkeypatch) as restarted:
        persisted = restarted.get("/api/api-server")

    assert initial.json()["max_initial_messages"] == 1000
    assert saved.status_code == 200
    assert saved.json()["max_initial_messages"] == 2
    assert too_small.status_code == too_large.status_code == 422
    assert accepted.status_code == 200, accepted.text
    assert rejected.status_code == 422
    assert rejected.json()["error"] == {
        "message": "messages cannot contain more than 2 items.",
        "type": "invalid_request_error",
        "param": "messages",
        "code": "input_messages_too_many",
    }
    assert rejected_sessions["total"] == 0
    assert len(rejected_history["items"]) == 1
    assert "input_messages_too_many" in rejected_history["items"][0]["summary"]
    assert persisted.json()["max_initial_messages"] == 2


def test_unused_openai_fields_are_ignored_without_overriding_model_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_model_blocks: list[dict] = []

    def configured_model(block, _credential, _http_clients):
        seen_model_blocks.append(dict(block))
        return ToolCompatibleFakeListChatModel(responses=["configured reply"])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            configured_model,
        )
        primary = create_primary(
            client,
            provider_settings={
                "temperature": 0.25,
                "top_p": 0.8,
                "max_completion_tokens": 2048,
            },
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Use saved settings."}],
                "stream": False,
                "temperature": 1.5,
                "top_p": 0.1,
                "max_tokens": 3,
                "presence_penalty": 2,
                "frequency_penalty": 2,
                "timeout": 1,
                "metadata": {"client": "fixture"},
                "client_extension": {"future_control": True},
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "configured reply"
    assert len(seen_model_blocks) == 1
    assert seen_model_blocks[0]["provider_settings"] == {
        "temperature": 0.25,
        "top_p": 0.8,
        "max_completion_tokens": 2048,
    }


def test_missing_required_output_block_fails_before_provider_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    provider_calls = 0

    def provider_model(_block, _credential):
        nonlocal provider_calls
        provider_calls += 1
        return FakeListChatModel(responses=["must not run"])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            provider_model,
        )
        primary = create_primary(client)
        output_id = capability_reference_id(primary, "output-mode")
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute("DELETE FROM blocks WHERE id = ?", (output_id,))
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not fall back."}],
            },
        )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "assembly.reference_not_found"
    assert provider_calls == 0


def test_invalid_stored_output_mode_is_preserved_and_rejected_before_user_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    marker = tmp_path / "custom-tool-must-not-run.txt"
    provider_calls = 0

    def provider_model(_block, _credential):
        nonlocal provider_calls
        provider_calls += 1
        return FakeListChatModel(responses=["must not run"])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            provider_model,
        )
        primary = create_primary(client)
        tools_dir = tmp_path / "data" / "resources" / "custom_tools"
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / "side_effect_tool.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
            "from langchain.tools import tool\n"
            "@tool\n"
            "def side_effect_tool(value: str) -> str:\n"
            '    """Return the supplied value."""\n'
            "    return value\n",
            encoding="utf-8",
        )
        custom = client.post(
            "/api/blocks/custom-tool",
            json={"name": "Selected side effect", "tools": ["side_effect_tool"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-tool", "block_id": custom["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text

        output_id = capability_reference_id(primary, "output-mode")
        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM blocks WHERE id = ?", (output_id,)
            ).fetchone()
            invalid_payload = json.loads(row[0])
            invalid_payload["event_templates"]["assistant_text"]["template"] = (
                "LONG OLD TEMPLATE THAT MUST REMAIN AVAILABLE: {{message}}"
            )
            invalid_payload["event_templates"]["assistant_text"][
                "start_template"
            ] = "<legacy>"
            serialized = json.dumps(invalid_payload, ensure_ascii=False)
            connection.execute(
                "UPDATE blocks SET payload = ? WHERE id = ?",
                (serialized, output_id),
            )

        stored = client.get(f"/api/blocks/output-mode/{output_id}")
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )
        with closing(sqlite3.connect(database_path)) as connection, connection:
            persisted = connection.execute(
                "SELECT payload FROM blocks WHERE id = ?", (output_id,)
            ).fetchone()[0]

    assert stored.status_code == 200
    assert (
        stored.json()["event_templates"]["assistant_text"]["start_template"]
        == "<legacy>"
    )
    assert stored.json()["event_templates"]["assistant_text"]["template"].startswith(
        "LONG OLD TEMPLATE"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "assembly.referenced_block_invalid"
    assert provider_calls == 0
    assert not marker.exists()
    assert persisted == serialized
