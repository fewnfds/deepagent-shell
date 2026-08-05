from __future__ import annotations

from .support import *

def test_real_provider_finish_reason_reaches_both_api_transports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class IncompleteExecution:
        usage = {
            "input_tokens": 5,
            "output_tokens": 8,
            "total_tokens": 13,
            "reasoning_tokens": 6,
        }
        finish_reason = "length"
        finish_reason_source = "response_metadata.finish_reason"
        response_blocks = []
        media_assets = []

        async def run(self):
            return "partial answer", dict(self.usage)

        async def stream_text(self):
            yield "partial answer"

    async def start_incomplete(*_args, **_kwargs):
        return IncompleteExecution()

    monkeypatch.setattr(
        "agent_shell.runtime.agent_runtime.AgentRuntime.start",
        start_incomplete,
    )
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        request = {
            "model": primary["name"],
            "messages": [{"role": "user", "content": "finish reason"}],
        }
        plain = client.post("/v1/chat/completions", json=request)
        streamed = client.post(
            "/v1/chat/completions", json={**request, "stream": True}
        )
        diagnostics = client.get(
            "/api/event-feed",
            params=event_feed_params(source="runtime", query="reasoning_tokens=6"),
        ).json()

    plain_payload = plain.json()
    final_stream_chunk = [
        json.loads(line.removeprefix("data: "))
        for line in streamed.text.splitlines()
        if line.startswith("data: {")
    ][-1]
    for payload in (plain_payload, final_stream_chunk):
        assert payload["choices"][0]["finish_reason"] == "length"
        assert payload["usage"]["completion_tokens_details"] == {
            "reasoning_tokens": 6
        }
        assert payload["agent_shell"]["termination"] == {
            "status": "incomplete",
            "finish_reason": "length",
            "category": "length",
            "source": "response_metadata.finish_reason",
            "message": (
                "The provider ended generation because its output limit was reached."
            ),
        }

    assert diagnostics["total"] == 2
    assert not (tmp_path / "data" / "logs" / "runtime.log").exists()

@pytest.mark.parametrize(
    ("failure_target", "stream"),
    [
        ("agent_session", False),
        ("api_history", True),
    ],
)
def test_observation_storage_failure_does_not_replace_primary_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_target: str,
    stream: bool,
) -> None:
    private_detail = f"{failure_target}-private-storage-detail"
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)

        def fail_record(*_args, **_kwargs):
            raise OSError(private_detail)

        if failure_target == "agent_session":
            monkeypatch.setattr(client.app.state.agent_sessions, "record_run", fail_record)
            expected_code = "agent_session_record_failed"
        else:
            monkeypatch.setattr(
                "agent_shell.storage.api_server.ApiServerStore.add_message_history",
                fail_record,
            )
            expected_code = "api_history_record_failed"

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "keep the main result"}],
                "stream": stream,
            },
        )
        diagnostics = client.get(
            "/api/event-feed",
            params=event_feed_params(source="runtime", query=expected_code),
        ).json()

        if failure_target == "agent_session":
            history = client.get(
                "/api/event-feed",
                params=event_feed_params(source="api_call", query="keep the main result"),
            ).json()
            assert len(history["items"]) == 1
        else:
            session = client.get(
                f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
            ).json()
            assert session["runs"][0]["status"] == "completed"
    assert response.status_code == 200, response.text
    if stream:
        assert streamed_content(response) == "runtime reply"
        assert response.text.rstrip().endswith("data: [DONE]")
    else:
        assert response.json()["choices"][0]["message"]["content"] == "runtime reply"
    error = next(item for item in diagnostics["items"] if expected_code in item["summary"])
    assert error["level"] == "error"
    assert private_detail not in json.dumps(diagnostics, ensure_ascii=False)
    assert not (tmp_path / "data" / "logs" / "runtime.log").exists()

def test_closing_primary_stream_records_client_disconnected_terminal_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def close_after_first_chunk(client: TestClient, model: str) -> tuple[str, int]:
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": "close after role"}],
                "stream": True,
            }
        ).encode()
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {"request_id": "close-stream-after-role"},
            "app": client.app,
        }
        def nested_routes(items):
            for item in items:
                yield item
                nested = getattr(item, "routes", None)
                if nested is None:
                    nested = getattr(getattr(item, "original_router", None), "routes", ())
                yield from nested_routes(nested)

        route = next(
            item
            for item in nested_routes(client.app.routes)
            if getattr(item, "path", "") == "/v1/chat/completions"
            and "POST" in getattr(item, "methods", set())
        )
        response = await route.endpoint(Request(scope, receive))
        before = client.app.state.agent_sessions.list_sessions(
            page=1, page_size=20, query="", agent="", status=""
        )
        first_chunk = await anext(response.body_iterator)
        assert '"role":"assistant"' in first_chunk
        await response.body_iterator.aclose()
        return response.headers["x-agent-session-id"], before["total"]

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        session_id, running_rows = asyncio.run(
            close_after_first_chunk(client, primary["name"])
        )
        session = client.get(f"/api/agent-sessions/{session_id}").json()
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="close after role"),
        ).json()

    assert running_rows == 0
    assert session["runs"][0]["status"] == "client_disconnected"
    assert session["runs"][0]["finished_at"]
    assert len(history["items"]) == 1
    assert "client_disconnected" in history["items"][0]["summary"]

def test_closing_non_stream_request_cancels_execution_and_records_disconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class WaitingExecution:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False
            self.usage = {}
            self.response_blocks = []
            self.media_assets = []

        async def run(self):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def close_after_body(
        client: TestClient,
        model: str,
        execution: WaitingExecution,
    ):
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "user", "content": "cancel non-stream work"}
                ],
                "stream": False,
            }
        ).encode()
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/chat/completions",
            "raw_path": b"/v1/chat/completions",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
            "state": {"request_id": "close-non-stream"},
            "app": client.app,
        }

        def nested_routes(items):
            for item in items:
                yield item
                nested = getattr(item, "routes", None)
                if nested is None:
                    nested = getattr(
                        getattr(item, "original_router", None), "routes", ()
                    )
                yield from nested_routes(nested)

        route = next(
            item
            for item in nested_routes(client.app.routes)
            if getattr(item, "path", "") == "/v1/chat/completions"
            and "POST" in getattr(item, "methods", set())
        )
        response = await route.endpoint(Request(scope, receive))
        await asyncio.wait_for(execution.started.wait(), timeout=1)
        return response

    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        execution = WaitingExecution()

        async def start_waiting(*_args, **_kwargs):
            return execution

        monkeypatch.setattr(
            "agent_shell.runtime.agent_runtime.AgentRuntime.start",
            start_waiting,
        )
        response = asyncio.run(close_after_body(client, primary["name"], execution))
        session_id = response.headers["x-agent-session-id"]
        session = client.get(f"/api/agent-sessions/{session_id}").json()
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="cancel non-stream work"),
        ).json()

    assert response.status_code == 499
    assert execution.cancelled is True
    assert session["runs"][0]["status"] == "client_disconnected"
    assert len(history["items"]) == 1
    detail = json.loads(history["items"][0]["inline_content"])["entry"]
    assert detail["status"] == "client_disconnected"
    assert detail["http_status"] == 499

def test_reused_client_request_id_does_not_conflict_with_session_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = {"X-Request-ID": "client-retry-1"}
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        payload = {
            "model": primary["name"],
            "messages": [{"role": "user", "content": "retry safely"}],
        }
        first = client.post("/v1/chat/completions", headers=headers, json=payload)
        second = client.post("/v1/chat/completions", headers=headers, json=payload)
        sessions = client.get(
            "/api/agent-sessions", params={"query": "client-retry-1"}
        ).json()

    assert first.status_code == second.status_code == 200
    assert first.headers["x-request-id"] == second.headers["x-request-id"] == "client-retry-1"
    assert first.headers["x-agent-session-id"] != second.headers["x-agent-session-id"]
    assert sessions["total"] == 2
