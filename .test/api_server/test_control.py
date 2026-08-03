from __future__ import annotations

from .support import *


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
