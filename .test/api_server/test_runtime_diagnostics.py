from __future__ import annotations

from agent_shell.provider_http import ProviderStreamError

from .support import *

def test_runtime_diagnostics_exposes_safe_errors_and_optional_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive_detail = "diagnostic-sensitive-detail"
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        enabled = client.put("/api/runtime-diagnostics", json={"verbose": True})
        completed = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "private user body"}],
            },
        )

        def fail_start(*_args, **_kwargs):
            raise RuntimeError(sensitive_detail)

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_workflow",
            fail_start,
        )
        failed = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "another private body"}],
            },
        )
        diagnostics = client.get(
            "/api/event-feed", params=event_feed_params(source="runtime", page_size=100)
        ).json()

    assert enabled.json()["verbose"] is True
    assert completed.status_code == 200
    assert failed.status_code == 500
    entries = diagnostics["items"]
    records = [json.loads(item["inline_content"])["entry"] for item in entries]
    assert any(item["level"] == "debug" and "lifecycle" in item["message"] for item in records)
    error = next(item for item in records if item["level"] == "error")
    assert error["code"] == "internal_error"
    assert error["request_id"] == failed.headers["x-request-id"]
    assert error["exception_type"] == "RuntimeError"
    wire = json.dumps(diagnostics, ensure_ascii=False)
    assert sensitive_detail not in wire
    assert "private user body" not in wire
    assert "another private body" not in wire
    assert "provider-test-secret" not in wire
    assert str(tmp_path) not in wire
    assert not (tmp_path / "data" / "logs" / "runtime.log").exists()

def test_runtime_diagnostics_preserves_safe_provider_stream_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive_detail = "provider-private disconnect detail"
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)

        def fail_start(*_args, **_kwargs):
            stream_error = ProviderStreamError(curl_code=56)
            stream_error.__cause__ = RuntimeError(sensitive_detail)
            raise RuntimeError("outer-private-detail") from stream_error

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_workflow",
            fail_start,
        )
        failed = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "private user body"}],
            },
        )
        diagnostics = client.get(
            "/api/event-feed", params=event_feed_params(source="runtime", page_size=100)
        ).json()

    wire = json.dumps(diagnostics, ensure_ascii=False)
    assert failed.status_code == 500
    assert "curl_code=56 curl_error=RECV_ERROR" in wire
    assert sensitive_detail not in wire
    assert "outer-private-detail" not in wire
    assert "private user body" not in wire

def test_unexpected_runtime_start_error_is_redacted_and_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive_detail = "unexpected-sensitive-runtime-detail"
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)

        def fail_start(*_args, **_kwargs):
            raise RuntimeError(sensitive_detail)

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_workflow",
            fail_start,
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "record internal failure"}],
            },
        )
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="record internal failure"),
        ).json()
        detail = client.get(
            f"/api/event-feed/api_call/{history['items'][0]['id']}/download"
        ).json()["entry"]

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert sensitive_detail not in response.text
    assert len(history["items"]) == 1
    assert "internal_error" in history["items"][0]["summary"]
    assert detail["http_status"] == 500
    assert sensitive_detail not in json.dumps(detail)

def test_event_hub_pushes_interception_notifications_without_bodies() -> None:
    async def scenario() -> str:
        hub = ApiServerEventHub()
        stream = hub.stream()
        assert await anext(stream) == ": connected\n\n"
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await hub.publish({"type": "interception_changed", "id": "record-id"})
        event = await asyncio.wait_for(pending, timeout=1)
        await stream.aclose()
        return event

    event = asyncio.run(scenario())
    assert json.loads(event.removeprefix("data: ")) == {
        "type": "interception_changed",
        "id": "record-id",
    }
