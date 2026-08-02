from __future__ import annotations

from agent_shell.provider_http import ProviderStreamError

from .support import *


def retention_settings(value: int) -> dict[str, int]:
    return {"retention_limit": value, "max_retention_limit": 10_000}


def test_agent_session_header_groups_multiple_requests_and_deletes_as_one_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        first = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "first turn"}],
            },
        )
        session_id = first.headers["x-agent-session-id"]
        second = client.post(
            "/v1/chat/completions",
            headers={"X-Agent-Session-ID": session_id},
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "user", "content": "first turn"},
                    {"role": "assistant", "content": "runtime reply"},
                    {"role": "user", "content": "second turn"},
                ],
            },
        )
        listing = client.get("/api/agent-sessions").json()
        detail = client.get(f"/api/agent-sessions/{session_id}").json()
        request_match = client.get(
            "/api/agent-sessions",
            params={"query": detail["runs"][1]["request_id"]},
        ).json()
        deleted = client.delete(f"/api/agent-sessions/{session_id}")

        assert first.status_code == second.status_code == 200
        assert second.headers["x-agent-session-id"] == session_id
        assert listing["total"] == 1
        assert listing["items"][0]["model_call_count"] == 2
        assert request_match["total"] == 1
        assert [run["status"] for run in detail["runs"]] == ["completed", "completed"]
        assert detail["runs"][0]["input_messages"][0]["content"] == "first turn"
        assert detail["runs"][1]["input_messages"][-1]["content"] == "second turn"
        assert all(
            any(item["kind"] == "model_request" for item in run["timeline"])
            for run in detail["runs"]
        )
        assert all(
            any(item["kind"] == "model_response" for item in run["timeline"])
            for run in detail["runs"]
        )
        response_event = next(
            item
            for item in detail["runs"][0]["timeline"]
            if item["kind"] == "model_response"
        )
        assert response_event["data"]["is_primary"] is True
        assert isinstance(response_event["data"]["response_metadata"], dict)
        assert isinstance(response_event["data"]["usage"], dict)
        assert deleted.json() == {"deleted": True}
        assert client.get(f"/api/agent-sessions/{session_id}").status_code == 404


def test_agent_session_bulk_delete_uses_the_listing_filters_and_whole_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        store = client.app.state.agent_sessions
        for index, (session_id, request_id, agent_name, status) in enumerate(
            (
                ("session-alpha", "request-alpha", "Primary Agent", "completed"),
                ("session-beta", "request-beta", "Worker", "failed"),
            )
        ):
            store.record_run(
                session_id=session_id,
                request_id=request_id,
                model="model-1",
                agent_name=agent_name,
                started_at=f"2026-01-02T03:0{index}:00Z",
                finished_at=f"2026-01-02T03:0{index}:05Z",
                status=status,
                input_messages=[],
                timeline=[],
                response_text="done",
                error_code="failed" if status == "failed" else None,
            )

        matching = client.get(
            "/api/agent-sessions",
            params={"query": "ＡＬＰＨＡ", "agent": "primary", "status": "completed"},
        ).json()
        deleted = client.post(
            "/api/agent-sessions/delete",
            json={"query": "ＡＬＰＨＡ", "agent": "primary", "status": "completed"},
        )

        assert matching["total"] == 1
        assert deleted.json() == {"deleted": 1}
        assert client.get("/api/agent-sessions/session-alpha").status_code == 404
        assert client.get("/api/agent-sessions/session-beta").status_code == 200


def test_agent_session_timeline_loads_large_step_json_only_from_step_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    large_input = f"input-{'i' * 5000}"
    large_result = f"result-{'r' * 5000}"
    large_response = f"response-{'o' * 5000}"
    with make_client(tmp_path, monkeypatch) as client:
        client.app.state.agent_sessions.record_run(
            session_id="lazy-session",
            request_id="lazy-request",
            model="model-1",
            agent_name="Primary",
            started_at="2026-01-02T03:04:00Z",
            finished_at="2026-01-02T03:04:05Z",
            status="completed",
            input_messages=[{"role": "user", "content": large_input}],
            timeline=[
                {
                    "sequence": 1,
                    "kind": "model_request",
                    "timestamp": "2026-01-02T03:04:01Z",
                    "data": {
                        "model": {"name": "provider-model"},
                        "messages": [{"role": "user", "content": large_input}],
                        "tools": [{"name": "lookup"}],
                    },
                },
                {
                    "sequence": 2,
                    "kind": "tool_result",
                    "timestamp": "2026-01-02T03:04:02Z",
                    "data": {"tool_name": "lookup", "output": large_result},
                },
            ],
            response_text=large_response,
            error_code=None,
        )

        timeline = client.get("/api/agent-sessions/lazy-session/timeline")
        run = timeline.json()["runs"][0]
        input_step = client.get(
            f"/api/agent-sessions/lazy-session/runs/{run['id']}/steps/input"
        )
        event_step = client.get(
            f"/api/agent-sessions/lazy-session/runs/{run['id']}/steps/event-1"
        )
        output_step = client.get(
            f"/api/agent-sessions/lazy-session/runs/{run['id']}/steps/output"
        )
        missing_step = client.get(
            f"/api/agent-sessions/lazy-session/runs/{run['id']}/steps/event-99"
        )

    assert timeline.status_code == 200
    assert run["input_message_count"] == 1
    assert run["timeline"][0]["data"] == {
        "model_name": "provider-model",
        "message_count": 1,
        "tool_count": 1,
    }
    assert run["timeline"][1]["data"]["output"].endswith("…")
    assert large_input not in timeline.text
    assert large_result not in timeline.text
    assert large_response not in timeline.text
    assert input_step.json()["data"]["messages"][0]["content"] == large_input
    assert event_step.json()["data"]["output"] == large_result
    assert output_step.json()["data"]["response_text"] == large_response
    assert missing_step.status_code == 404
    assert missing_step.json()["detail"]["code"] == "agent_session_step_not_found"


def test_agent_session_history_aggregates_complete_token_usage_without_schema_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def response_event(
        sequence: int,
        *,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int | None,
    ) -> dict[str, object]:
        usage: dict[str, object] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        if reasoning_tokens is not None:
            usage["output_token_details"] = {"reasoning": reasoning_tokens}
        return {
            "sequence": sequence,
            "kind": "model_response",
            "timestamp": f"2026-01-02T03:04:0{sequence}Z",
            "data": {"usage": usage},
        }

    with make_client(tmp_path, monkeypatch) as client:
        store = client.app.state.agent_sessions
        store.record_run(
            session_id="usage-session",
            request_id="usage-request",
            model="model-1",
            agent_name="Primary",
            started_at="2026-01-02T03:04:00Z",
            finished_at="2026-01-02T03:04:05Z",
            status="completed",
            input_messages=[],
            timeline=[
                response_event(
                    1, input_tokens=10, output_tokens=8, reasoning_tokens=3
                ),
                response_event(
                    2, input_tokens=20, output_tokens=15, reasoning_tokens=4
                ),
            ],
            response_text="done",
            error_code=None,
        )
        store.record_run(
            session_id="usage-unreported",
            request_id="usage-unreported-request",
            model="model-1",
            agent_name="Primary",
            started_at="2026-01-02T03:05:00Z",
            finished_at="2026-01-02T03:05:05Z",
            status="completed",
            input_messages=[],
            timeline=[
                response_event(
                    1, input_tokens=2, output_tokens=5, reasoning_tokens=None
                )
            ],
            response_text="done",
            error_code=None,
        )

        timeline = client.get("/api/agent-sessions/usage-session/timeline").json()
        download = client.get("/api/agent-sessions/usage-session").json()
        unreported = client.get(
            "/api/agent-sessions/usage-unreported/timeline"
        ).json()

    expected = {
        "input_tokens": 30,
        "non_reasoning_output_tokens": 16,
        "reasoning_output_tokens": 7,
    }
    assert timeline["token_usage"] == expected
    assert download["token_usage"] == expected
    assert unreported["token_usage"] == {
        "input_tokens": 2,
        "non_reasoning_output_tokens": None,
        "reasoning_output_tokens": None,
    }

def test_runtime_diagnostics_exposes_safe_errors_and_optional_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sensitive_detail = "diagnostic-sensitive-detail"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        enabled = client.put("/api/runtime-diagnostics", json={"verbose": True})
        completed = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "private user body"}],
            },
        )

        def fail_start(*_args, **_kwargs):
            raise RuntimeError(sensitive_detail)

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_agent",
            fail_start,
        )
        failed = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
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
        primary = create_primary(client)

        def fail_start(*_args, **_kwargs):
            stream_error = ProviderStreamError(curl_code=56)
            stream_error.__cause__ = RuntimeError(sensitive_detail)
            raise RuntimeError("outer-private-detail") from stream_error

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_agent",
            fail_start,
        )
        failed = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
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
        primary = create_primary(client)

        def fail_start(*_args, **_kwargs):
            raise RuntimeError(sensitive_detail)

        monkeypatch.setattr(
            "agent_shell.runtime.request_snapshot.RequestRuntimeSnapshot.start_agent",
            fail_start,
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
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

def test_non_test_history_is_filterable_downloadable_and_batch_deletable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "history-inference-key"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        saved = client.put(
            "/api/api-server",
            json={"api_key": {"operation": "replace", "value": secret}},
        )
        assert saved.status_code == 200
        headers = {"Authorization": f"Bearer {secret}"}
        tbd = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "alpha-history"}],
            },
        )
        invalid_stream = client.post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "beta-history"}],
                "stream": "yes",
            },
        )
        client.put("/api/interception-test", json={"enabled": True})
        missing = client.post(
            "/v1/chat/completions",
            headers={
                **headers,
                "X-Agent-Session-ID": "invalid session id",
            },
            json={
                "model": "missing-primary",
                "messages": [{"role": "user", "content": "gamma-history"}],
                "stream": "yes",
            },
        )
        searched = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="beta-history"),
        ).json()
        completed_runtime = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="alpha-history"),
        ).json()
        missing_history = client.get(
            "/api/event-feed",
            params=event_feed_query_pairs(
                ("source", "api_call"),
                ("source", "interception"),
                ("query", "gamma-history"),
            ),
        ).json()
        missing_sessions = client.get(
            "/api/agent-sessions", params={"query": "gamma-history"}
        ).json()
        detail = client.get(
            "/api/event-feed/api_call/"
            f"{completed_runtime['items'][0]['id']}/download"
        ).json()["entry"]
        bulk = client.post(
            "/api/event-feed/delete",
            json={
                **EVENT_FEED_TEST_WINDOW,
                "source": ["api_call"],
                "level": [],
                "query": "",
            },
        )
        empty = client.get(
            "/api/event-feed", params=event_feed_params(source="api_call")
        ).json()

    assert tbd.status_code == 200
    assert invalid_stream.status_code == 422
    assert missing.status_code == 404
    assert len(searched["items"]) == 1
    assert "invalid_stream" in searched["items"][0]["summary"]
    assert len(completed_runtime["items"]) == 1
    assert missing_history["items"] == []
    assert missing_sessions["total"] == 0
    assert detail["agent_name"] == "Published Primary"
    assert detail["status"] == "completed"
    assert detail["finished_at"]
    assert "alpha-history" in detail["request_body"]
    response_body = json.loads(detail["response_body"])
    assert response_body["choices"][0]["message"]["content"] == "runtime reply"
    assert detail["response_content_type"] == "application/json"
    assert detail["http_status"] == 200
    assert secret not in json.dumps(detail)
    assert bulk.json() == {"deleted": 2}
    assert empty["items"] == []


def test_history_page_retention_limits_trim_oldest_records_and_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_paths = (
        "/api/api-server/history/retention",
        "/api/agent-sessions/retention",
        "/api/interception-test/records/retention",
    )

    def send_three(client: TestClient, primary: dict, prefix: str) -> None:
        for index in range(3):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": primary["name"],
                    "messages": [{"role": "user", "content": f"{prefix}-{index}"}],
                },
            )
            assert response.status_code == 200, response.text

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        for path in settings_paths:
            assert client.get(path).json() == retention_settings(20)
        send_three(client, primary, "retention")

        assert client.put(
            "/api/api-server/history/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        assert len(client.get(
            "/api/event-feed", params=event_feed_params(source="api_call", page_size=100)
        ).json()["items"]) == 2

        assert client.put(
            "/api/agent-sessions/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        sessions = client.get("/api/agent-sessions").json()
        assert sessions["total"] == 2

        client.put("/api/interception-test", json={"enabled": True})
        send_three(client, primary, "capture")
        assert client.put(
            "/api/interception-test/records/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        assert len(client.get(
            "/api/event-feed", params=event_feed_params(source="interception", page_size=100)
        ).json()["items"]) == 2

        diagnostics = client.app.state.runtime_diagnostics
        assert client.put(
            "/api/runtime-diagnostics/retention",
            json={"retention_limit": 2},
        ).json()["retention_limit"] == 2
        for index in range(3):
            diagnostics.request_started(
                request_id=f"runtime-{index}", model="model", agent_name="agent"
            )
        runtime = client.get(
            "/api/event-feed", params=event_feed_params(source="runtime", page_size=100)
        ).json()
        assert {item["request_id"] for item in runtime["items"]} == {
            "runtime-1",
            "runtime-2",
        }

    with make_client(tmp_path, monkeypatch) as restarted:
        for path in settings_paths:
            assert restarted.get(path).json() == retention_settings(2)
        assert restarted.get("/api/runtime-diagnostics").json()["retention_limit"] == 2


def test_agent_session_retention_keeps_or_deletes_every_run_as_one_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(client: TestClient, primary: dict, session_id: str, message: str) -> None:
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Agent-Session-ID": session_id},
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": message}],
            },
        )
        assert response.status_code == 200, response.text

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        run(client, primary, "session-old", "old first")
        run(client, primary, "session-old", "old second")
        run(client, primary, "session-middle", "middle first")
        run(client, primary, "session-middle", "middle second")
        run(client, primary, "session-new", "new only")

        updated = client.put(
            "/api/agent-sessions/retention",
            json={"retention_limit": 2},
        )
        listing = client.get("/api/agent-sessions").json()
        old = client.get("/api/agent-sessions/session-old")
        middle = client.get("/api/agent-sessions/session-middle").json()
        new = client.get("/api/agent-sessions/session-new").json()

    assert updated.json() == retention_settings(2)
    assert listing["total"] == 2
    assert {item["session_id"] for item in listing["items"]} == {
        "session-middle",
        "session-new",
    }
    assert old.status_code == 404
    assert [
        run_item["input_messages"][0]["content"] for run_item in middle["runs"]
    ] == ["middle first", "middle second"]
    assert len(new["runs"]) == 1

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
