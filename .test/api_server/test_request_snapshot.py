from __future__ import annotations

import threading

from .support import *


class SnapshotEchoModel(ToolCompatibleFakeListChatModel):
    started: ClassVar[threading.Event | None] = None
    release: ClassVar[threading.Event | None] = None

    async def _astream(self, messages, *args, **kwargs):
        if self.responses[0] == "provider-test-secret":
            assert self.started is not None
            assert self.release is not None
            self.started.set()
            await asyncio.to_thread(self.release.wait)
        async for chunk in super()._astream(messages, *args, **kwargs):
            yield chunk


def test_snapshot_keeps_model_resolution_and_assembly_on_one_committed_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        snapshot = client.app.state.agent_runtime.capture()
        renamed = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": "Renamed after capture",
                "capability_refs": primary["capability_refs"],
                "subagents": primary["subagents"],
            },
        )
        assert renamed.status_code == 200, renamed.text

        assert snapshot.primary_by_name(primary["name"])["id"] == primary["id"]
        assert snapshot.primary_by_name("Renamed after capture") is None

        next_snapshot = client.app.state.agent_runtime.capture()
        assert next_snapshot.primary_by_name(primary["name"]) is None
        assert next_snapshot.primary_by_name("Renamed after capture")["id"] == primary["id"]


def test_running_models_and_later_requests_use_the_latest_primary_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        renamed = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": "Live renamed Primary",
                "capability_refs": primary["capability_refs"],
                "subagents": primary["subagents"],
            },
        )
        assert renamed.status_code == 200, renamed.text
        models = client.get("/v1/models")
        old = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "old name"}],
            },
        )
        current = client.post(
            "/v1/chat/completions",
            json={
                "model": "Live renamed Primary",
                "messages": [{"role": "user", "content": "new name"}],
            },
        )

    assert [item["id"] for item in models.json()["data"]] == [
        "Live renamed Primary"
    ]
    assert old.status_code == 404
    assert old.json()["error"]["code"] == "model_not_found"
    assert current.status_code == 200, current.text


def test_captured_agent_build_never_falls_back_to_live_configuration_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        snapshot = client.app.state.agent_runtime.capture()
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute("DELETE FROM primary_agents")
            connection.execute("DELETE FROM subagent_overrides")
            connection.execute("DELETE FROM blocks")
            connection.execute("DELETE FROM provider_secrets")

        execution = snapshot.start_agent(
            primary["id"],
            [{"role": "user", "content": "Use only the captured configuration."}],
        )
        content, _usage = asyncio.run(execution.run())

    assert content == "runtime reply"


def test_running_crud_changes_only_later_agent_constructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    SnapshotEchoModel.started = started
    SnapshotEchoModel.release = release
    responses: dict[str, object] = {}

    def model_factory(_block, credential):
        return SnapshotEchoModel(responses=[credential or "missing"])

    def invoke_old(client: TestClient, model: str) -> None:
        responses["old"] = client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "old request"}],
            },
        )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model", model_factory
        )
        primary = create_primary(client)
        model_id = capability_reference_id(primary, "model")
        thread = threading.Thread(target=invoke_old, args=(client, primary["name"]))
        thread.start()
        try:
            assert started.wait(5), "the first Agent did not begin provider execution"
            updated = client.put(
                f"/api/blocks/model/{model_id}",
                json={
                    "name": "Published model",
                    "provider": "openai",
                    "base_url": "https://provider.example/v1",
                    "credential": "provider-new-secret",
                    "model": "provider-model",
                    "tool_choice": None,
                    "response_format": None,
                    "model_settings": {},
                },
            )
            assert updated.status_code == 200, updated.text
            current = client.post(
                "/v1/chat/completions",
                json={
                    "model": primary["name"],
                    "messages": [{"role": "user", "content": "new request"}],
                },
            )
        finally:
            release.set()
            thread.join(5)

    assert not thread.is_alive()
    old = responses["old"]
    assert old.status_code == 200, old.text
    assert old.json()["choices"][0]["message"]["content"] == "provider-test-secret"
    assert current.status_code == 200, current.text
    assert current.json()["choices"][0]["message"]["content"] == "provider-new-secret"


@pytest.mark.parametrize("stream", [False, True])
def test_stop_rejects_new_work_without_interrupting_an_existing_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stream: bool
) -> None:
    started = threading.Event()
    release = threading.Event()
    SnapshotEchoModel.started = started
    SnapshotEchoModel.release = release
    responses: dict[str, object] = {}

    def model_factory(_block, credential):
        return SnapshotEchoModel(responses=[credential or "missing"])

    def invoke(client: TestClient, model: str) -> None:
        responses["accepted"] = client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "finish after stop"}],
                "stream": stream,
            },
        )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model", model_factory
        )
        primary = create_primary(client)
        thread = threading.Thread(target=invoke, args=(client, primary["name"]))
        thread.start()
        try:
            assert started.wait(5), "the accepted request did not begin"
            stopped = client.post("/api/api-server/stop")
            rejected = client.post(
                "/v1/chat/completions",
                json={
                    "model": primary["name"],
                    "messages": [{"role": "user", "content": "must not start"}],
                },
            )
        finally:
            release.set()
            thread.join(5)

    assert stopped.json()["enabled"] is False
    assert rejected.status_code == 503
    assert rejected.json()["error"]["code"] == "api_server_stopped"
    assert not thread.is_alive()
    accepted = responses["accepted"]
    assert accepted.status_code == 200, accepted.text
    content = (
        streamed_content(accepted)
        if stream
        else accepted.json()["choices"][0]["message"]["content"]
    )
    assert content == "provider-test-secret"


def test_snapshot_capture_failure_is_safe_without_persisting_the_request_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_detail = "private snapshot failure detail"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)

        def fail_capture():
            raise OSError(private_detail)

        monkeypatch.setattr(client.app.state.agent_runtime, "capture", fail_capture)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "capture safely"}],
            },
        )
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="capture safely"),
        ).json()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "configuration_snapshot_failed"
    assert private_detail not in response.text
    assert history["items"] == []


def test_api_start_globally_validates_even_unreferenced_saved_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with make_client(tmp_path, monkeypatch) as client:
        create_primary(client)
        unused = client.post(
            "/api/blocks/system-prompt",
            json={"name": "Unused invalid draft", "system_prompt": "draft"},
        ).json()
        client.post("/api/api-server/stop")
        with closing(sqlite3.connect(database_path)) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM blocks WHERE id = ?", (unused["id"],)
            ).fetchone()
            payload = json.loads(row[0])
            payload["removed_field"] = True
            connection.execute(
                "UPDATE blocks SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), unused["id"]),
            )

        started = client.post("/api/api-server/start")

    assert started.status_code == 422
    detail = started.json()["detail"]
    assert detail["validation"]["stage"] == "api_start"
    assert any(
        issue["owner_id"] == unused["id"]
        and issue["code"] == "contract.unknown_field"
        for issue in detail["validation"]["issues"]
    )
