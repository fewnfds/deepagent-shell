from __future__ import annotations

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
        ([{"role": "user", "content": ["not", "text"]}], "input_message_content_unsupported"),
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


def test_request_larger_than_previous_one_mib_limit_is_retained_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = "忠实上下文" + ("x" * 1_100_000)

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": content}],
            },
        )
        history = client.get(
            "/api/event-feed", params=event_feed_params(source="api_call")
        ).json()
        detail = client.get(
            f"/api/event-feed/api_call/{history['items'][0]['id']}/download"
        ).json()["entry"]

    assert response.status_code == 200, response.text
    assert json.loads(detail["request_body"])["messages"][0]["content"] == content

def test_unused_openai_fields_are_ignored_without_overriding_model_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen_model_blocks: list[dict] = []

    def configured_model(block, _credential):
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

def test_api_key_is_write_only_and_takes_effect_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "page-inference-key"
    with make_client(tmp_path, monkeypatch) as client:
        initial = client.get("/v1/models")
        saved = client.put(
            "/api/api-server",
            json={"api_key": {"operation": "replace", "value": secret}},
        )
        rejected_legacy_field = client.put(
            "/api/api-server",
            json={
                "api_key": {"operation": "keep"},
                "test_message_limit": 20,
            },
        )
        missing = client.get("/v1/models", headers={"Authorization": ""})
        wrong = client.get(
            "/v1/models", headers={"Authorization": "Bearer wrong-key"}
        )
        allowed = client.get(
            "/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )
        status = client.get("/api/api-server")

    with ScopedAuthTestClient(create_app()) as restarted:
        persisted = restarted.get(
            "/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )

    assert initial.status_code == 200
    assert saved.status_code == 200
    assert rejected_legacy_field.status_code == 422
    assert saved.json()["api_key"] == {"configured": True}
    assert secret not in saved.text
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
    assert persisted.status_code == 200
    assert secret not in status.text
    assert "test_message_limit" not in status.json()

def test_interception_records_are_persistent_paged_searchable_and_deletable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordingFakeListChatModel.seen_messages = []
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: RecordingFakeListChatModel(
                responses=["provider must not run"]
            ),
        )
        primary = create_primary(client)
        enabled = client.put("/api/interception-test", json={"enabled": True})
        assert enabled.json() == {"enabled": True}
        for number in range(3):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": primary["name"],
                    "messages": [{"role": "user", "content": f"message-{number}"}],
                    "metadata": {"number": number},
                },
            )
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == INTERCEPTION_REPLY

        first_page = client.get(
            "/api/event-feed",
            params=event_feed_params(source="interception", page_size=2),
        ).json()
        searched = client.get(
            "/api/event-feed",
            params=event_feed_params(source="interception", query="message-1"),
        ).json()
        current = client.get(
            "/api/event-feed/interception/"
            f"{first_page['items'][0]['id']}/download"
        ).json()["entry"]
        assert len(first_page["items"]) == 2
        assert first_page["total"] == 3
        assert len(searched["items"]) == 1
        details = [
            json.loads(item["inline_content"])["entry"]
            for item in first_page["items"]
        ]
        assert all(item["name"] for item in details)
        assert all("request_raw_json" not in item for item in first_page["items"])
        assert json.loads(current["request_raw_json"])["metadata"]["number"] == 2
        assert RecordingFakeListChatModel.seen_messages == []
        assert client.get("/api/api-server/test-messages").status_code == 404

    with ScopedAuthTestClient(create_app()) as restarted:
        assert restarted.get("/api/interception-test").json() == {"enabled": True}
        persisted = restarted.get(
            "/api/event-feed", params=event_feed_params(source="interception", page_size=100)
        ).json()
        assert len(persisted["items"]) == 3
        deleted = restarted.post(
            "/api/event-feed/delete",
            json={
                **EVENT_FEED_TEST_WINDOW,
                "source": ["interception"],
                "level": [],
                "query": "",
            },
        )
        assert deleted.json() == {"deleted": 3}
        assert restarted.get(
            "/api/event-feed", params=event_feed_params(source="interception")
        ).json()["items"] == []

def test_start_stop_and_streaming_primary_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        stopped = client.post("/api/api-server/stop")
        unavailable = client.get("/v1/models")
        started = client.post("/api/api-server/start")
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "stream"}],
                "stream": True,
            },
        )
        streamed_session = client.get(
            f"/api/agent-sessions/{streamed.headers['x-agent-session-id']}"
        ).json()

    assert stopped.json()["enabled"] is False
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "api_server_stopped"
    assert started.json()["enabled"] is True
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert streamed_content(streamed) == "runtime reply"
    assert "data: [DONE]" in streamed.text
    assert streamed_session["runs"][0]["status"] == "completed"
    assert streamed_session["runs"][0]["response_text"] == "runtime reply"

def test_api_server_start_gate_rejects_invalid_primary_without_dynamic_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        client.post("/api/api-server/stop")

        def fail_dynamic_start(*_args, **_kwargs):
            raise AssertionError("API start must not build an Agent")

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_agent",
            fail_dynamic_start,
        )
        started = client.post("/api/api-server/start")
        assert started.status_code == 200
        client.post("/api/api-server/stop")

        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM primary_agents WHERE id = ?", (primary["id"],)
            ).fetchone()
            payload = json.loads(row[0])
            payload["capability_refs"][0]["block_id"] = (
                "00000000-0000-0000-0000-000000000000"
            )
            connection.execute(
                "UPDATE primary_agents SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), primary["id"]),
            )

        rejected = client.post("/api/api-server/start")
        status = client.get("/api/api-server")
        models = client.get("/v1/models")
        repository = client.get("/api/validation/repository")
        admin = client.get("/admin")

    assert rejected.status_code == 422
    detail = rejected.json()["detail"]
    assert detail["code"] == "configuration_validation_failed"
    assert detail["validation"]["stage"] == "api_start"
    assert any(
        issue["code"] == "assembly.reference_not_found"
        for issue in detail["validation"]["issues"]
    )
    assert status.json()["enabled"] is False
    assert models.status_code == 503
    assert models.json()["error"]["code"] == "api_server_stopped"
    assert repository.json()["valid"] is False
    assert admin.status_code == 200

    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "UPDATE api_server_settings SET enabled = 1 WHERE singleton = 1"
        )
    with ScopedAuthTestClient(create_app()) as restarted:
        assert restarted.get("/api/api-server").json()["enabled"] is False
        assert restarted.get("/admin").status_code == 200


def test_missing_model_request_fields_block_repository_primary_and_api_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        client.post("/api/api-server/stop")
        model_id = capability_reference_id(primary, "model")

        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM blocks WHERE id = ?", (model_id,)
            ).fetchone()
            payload = json.loads(row[0])
            for field in ("tool_choice", "response_format", "model_settings"):
                payload.pop(field)
            connection.execute(
                "UPDATE blocks SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), model_id),
            )

        repository = client.get("/api/validation/repository").json()
        primary_draft = client.post(
            "/api/validation/draft",
            json={
                "target": {"kind": "primary"},
                "payload": {
                    key: value for key, value in primary.items() if key != "id"
                },
            },
        ).json()
        rejected = client.post("/api/api-server/start")
        status = client.get("/api/api-server").json()

    assert repository["valid"] is False
    assert {
        issue["path"]
        for issue in repository["issues"]
        if issue["owner_id"] == model_id
        and issue["code"] == "contract.field_required"
    } == {"tool_choice", "response_format", "model_settings"}

    assert primary_draft["valid"] is False
    assert any(
        issue["code"] == "assembly.referenced_block_invalid"
        and issue["path"] == "capability_refs.model"
        for issue in primary_draft["issues"]
    )

    assert rejected.status_code == 422
    start_report = rejected.json()["detail"]["validation"]
    assert any(
        issue["owner_id"] == model_id
        and issue["code"] == "contract.field_required"
        for issue in start_report["issues"]
    )
    assert status["enabled"] is False


def test_restart_does_not_rewrite_running_state_when_start_validation_crashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        assert client.get("/api/api-server").json()["enabled"] is True

    def fail_validation(_self):
        raise RuntimeError("unexpected validation failure")

    monkeypatch.setattr(
        "agent_shell.validation.service.ConfigurationValidationService.validate_api_start",
        fail_validation,
    )

    with pytest.raises(RuntimeError, match="unexpected validation failure"):
        create_app()

    with closing(sqlite3.connect(database_path)) as connection:
        enabled = connection.execute(
            "SELECT enabled FROM api_server_settings WHERE singleton = 1"
        ).fetchone()[0]
    assert enabled == 1

def test_api_start_reports_primary_contract_and_referenced_block_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        client.post("/api/api-server/stop")

        output_id = next(
            item["block_id"]
            for item in primary["capability_refs"]
            if item["type"] == "output-mode"
        )
        with closing(sqlite3.connect(database_path)) as connection, connection:
            primary_payload = json.loads(
                connection.execute(
                    "SELECT payload FROM primary_agents WHERE id = ?", (primary["id"],)
                ).fetchone()[0]
            )
            primary_payload["subagents"] = [
                {
                    "enabled": True,
                    "name": "worker",
                    "description": "Handle delegated work.",
                    "subagent_override_id": "",
                    "use_current_primary": True,
                    "primary_agent_id": "",
                    "inherit_all": True,
                }
            ]
            output_payload = json.loads(
                connection.execute(
                    "SELECT payload FROM blocks WHERE id = ?", (output_id,)
                ).fetchone()[0]
            )
            output_payload["event_templates"]["other"] = {
                "enabled": False,
                "template": "{{message}}",
            }
            connection.execute(
                "UPDATE primary_agents SET payload = ? WHERE id = ?",
                (json.dumps(primary_payload, ensure_ascii=False), primary["id"]),
            )
            connection.execute(
                "UPDATE blocks SET payload = ? WHERE id = ?",
                (json.dumps(output_payload, ensure_ascii=False), output_id),
            )

        rejected = client.post("/api/api-server/start")

    assert rejected.status_code == 422
    issues = rejected.json()["detail"]["validation"]["issues"]
    assert {issue["path"] for issue in issues} == {
        "subagents[0].enabled",
        "subagents[0].use_current_primary",
        "subagents[0].primary_agent_id",
        "subagents[0].inherit_all",
        "capability_refs.output-mode",
        "event_templates.other.[key]",
    }
    assert sum(issue["code"] == "contract.unknown_field" for issue in issues) == 4
    assert any(
        issue["code"] == "assembly.referenced_block_invalid"
        and "Published output" in issue["message"]
        for issue in issues
    )

def test_api_start_uses_safe_ast_tool_names_without_importing_user_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    tools_dir.mkdir(parents=True)
    marker = tmp_path / "api-start-must-not-import.txt"
    tool_file = tools_dir / "changing_tool.py"

    def write_tool(tool_name: str) -> None:
        tool_file.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('imported')\n"
            "from langchain_core.tools import tool\n"
            f"@tool({tool_name!r})\n"
            "def changing_tool(value: str) -> str:\n"
            '    """Tool whose declared name changes between gates."""\n'
            "    return value\n",
            encoding="utf-8",
        )

    write_tool("safe_runtime_name")
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        todo = client.post(
            "/api/blocks/todo-list", json={"name": "AST gate Todo"}
        ).json()
        custom = client.post(
            "/api/blocks/custom-tool",
            json={"name": "AST gate tool", "tools": ["changing_tool"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "todo-list", "block_id": todo["id"]},
                    {"type": "custom-tool", "block_id": custom["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        assert not marker.exists()
        client.post("/api/api-server/stop")

        write_tool("write_todos")
        rejected = client.post("/api/api-server/start")

    assert rejected.status_code == 422
    assert any(
        issue["code"] == "assembly.tool_name_conflict"
        for issue in rejected.json()["detail"]["validation"]["issues"]
    )
    assert not marker.exists()
