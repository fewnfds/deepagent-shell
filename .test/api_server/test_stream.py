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

def test_selected_output_mode_wraps_the_same_timeline_for_both_transports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = attach_output_mode(
            client,
            create_primary(client),
            filter_mappings=[
                {"field": "lifecycle.phase", "value": "start"}
            ],
        )
        request = {
            "model": primary["name"],
            "messages": [{"role": "user", "content": "show the timeline"}],
        }
        plain = client.post("/v1/chat/completions", json=request)
        streamed = client.post(
            "/v1/chat/completions", json={**request, "stream": True}
        )

    expected = (
        "runtime reply"
        '<status phase="end">completed</status>'
    )
    assert plain.status_code == 200, plain.text
    assert plain.json()["choices"][0]["message"]["content"] == expected
    assert streamed.status_code == 200, streamed.text
    assert streamed_content(streamed) == expected
    assert streamed_content_parts(streamed) == [
        "runtime reply",
        '<status phase="end">completed</status>',
    ]
    assert streamed.text.rstrip().endswith("data: [DONE]")

def test_saved_system_prompt_and_complete_text_history_reach_deep_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordingFakeListChatModel.seen_messages = []
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: RecordingFakeListChatModel(
                responses=["recorded"]
            ),
        )
        primary = create_primary(client)
        prompt = client.post(
            "/api/blocks/system-prompt",
            json={"name": "Runtime prompt", "system_prompt": "configured system"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "system-prompt", "block_id": prompt["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [
                    {"role": "system", "content": "upstream system"},
                    {"role": "user", "content": "first user"},
                    {"role": "assistant", "content": "prior answer"},
                    {"role": "user", "content": "latest user"},
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "recorded"
    assert len(RecordingFakeListChatModel.seen_messages) == 1
    seen = RecordingFakeListChatModel.seen_messages[0]
    assert [message.type for message in seen] == [
        "system",
        "system",
        "human",
        "ai",
        "human",
    ]
    assert seen[0].text == "configured system"
    assert "Filesystem Tools" not in seen[0].text
    assert [message.text for message in seen[1:]] == [
        "upstream system",
        "first user",
        "prior answer",
        "latest user",
    ]

def test_provider_failure_uses_stable_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingProviderModel(FakeMessagesListChatModel):
        def _generate(self, messages, *args, **kwargs):
            raise RuntimeError("private provider response details")

    model = FailingProviderModel(responses=[AIMessage(content="unused")])
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "fail safely"}],
            },
        )
        failed_session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "fail stream safely"}],
                "stream": True,
            },
        )
        streamed_session = client.get(
            f"/api/agent-sessions/{streamed.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_request_failed"
    assert "private provider response details" not in response.text
    assert failed_session["runs"][0]["status"] == "failed"
    assert failed_session["runs"][0]["error_code"] == "provider_request_failed"
    assert streamed.status_code == 200
    assert '"code":"provider_request_failed"' in streamed.text
    assert streamed_session["runs"][0]["status"] == "failed"
    assert streamed_session["runs"][0]["error_code"] == "provider_request_failed"

def test_model_request_settings_reach_the_final_langchain_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response_schema = {
        "title": "Answer",
        "description": "Structured answer returned by the model.",
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(
            client,
            model_request_settings={
                "tool_choice": "required",
                "response_format": response_schema,
                "model_settings": {"parallel_tool_calls": False},
            },
        )
        client.put("/api/interception-test", json={"enabled": True})
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Capture settings."}],
            },
        )
        feed = client.get(
            "/api/event-feed", params=event_feed_params(source="interception")
        ).json()
        entry = client.get(
            "/api/event-feed/interception/"
            f"{feed['items'][0]['id']}/download"
        ).json()["entry"]

    captured = json.loads(entry["model_request_raw_json"])
    assert response.status_code == 200, response.text
    assert captured["tool_choice"] == "required"
    assert captured["model_settings"] == {"parallel_tool_calls": False}
    assert captured["response_format"]["value"]["schema"] == response_schema


def test_global_interception_captures_final_moved_prompt_tools_and_raw_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordingFakeListChatModel.seen_messages = []
    marker_source = (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "from langchain_core.messages import SystemMessage\n"
        "class MarkerMiddleware(AgentMiddleware):\n"
        "    def _mark(self, request):\n"
        "        blocks = list(request.system_message.content_blocks) if request.system_message else []\n"
        "        blocks.append({'type': 'text', 'text': '\\n\\nCUSTOM'})\n"
        "        return request.override(system_message=SystemMessage(content=blocks))\n"
        "    def wrap_model_call(self, request, handler):\n"
        "        return handler(self._mark(request))\n"
        "    async def awrap_model_call(self, request, handler):\n"
        "        return await handler(self._mark(request))\n"
        "middleware = MarkerMiddleware()\n"
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: RecordingFakeListChatModel(
                responses=["provider must not run"]
            ),
        )
        primary = create_primary(client)
        write_automation_script(
            tmp_path,
            "capture-message-rewrite",
            "async def run(ctx):\n"
            "    tag = str(ctx.config.get('tag', ''))\n"
            "    replacement = str(ctx.config.get('replacement', ''))\n"
            "    for message in ctx.messages:\n"
            "        if message.get('role') == 'user':\n"
            "            message['content'] = message['content'].replace(tag, replacement)\n",
        )
        workflow = create_hook_workflow(
            client,
            "Captured message preparation",
            request_prepare=[
                {
                    "script_id": "capture-message-rewrite",
                    "config": {
                        "tag": "|||agent_prompt|||",
                        "replacement": "PRESET",
                    },
                }
            ],
        )
        prompt = client.post(
            "/api/blocks/system-prompt",
            json={"name": "Captured prompt", "system_prompt": "PRIMARY"},
        ).json()
        todo = client.post(
            "/api/blocks/todo-list",
            json={"name": "Captured Todo", "system_prompt_override": "TODO"},
        ).json()
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Captured custom Middleware",
                "middlewares": [
                    {"name": "Captured marker", "enabled": True, "source": marker_source}
                ],
            },
        ).json()
        output_mode = client.post(
            "/api/blocks/output-mode",
            json=output_mode_payload("Interception timeline"),
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *[
                        item
                        for item in primary["capability_refs"]
                        if item["type"] != "output-mode"
                    ],
                    {"type": "system-prompt", "block_id": prompt["id"]},
                    {"type": "todo-list", "block_id": todo["id"]},
                    {"type": "custom-middleware", "block_id": custom["id"]},
                    {"type": "output-mode", "block_id": output_mode["id"]},
                ],
                "subagents": [],
                "automation": {
                    "hook_workflow_id": workflow["id"],
                    "lifecycle_workflow_id": "",
                },
            },
        )
        assert updated.status_code == 200, updated.text
        armed = client.put("/api/interception-test", json={"enabled": True})
        assert armed.status_code == 200, armed.text
        request_payload = {
            "model": primary["name"],
            "messages": [
                {"role": "system", "content": "CLIENT HEAD"},
                {"role": "user", "content": "before|||agent_prompt|||after"},
            ],
            "stream": True,
        }
        raw_json = json.dumps(
            request_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        intercepted = client.post(
            "/v1/chat/completions",
            content=raw_json,
            headers={"Content-Type": "application/json"},
        )
        records = client.get(
            "/api/event-feed", params=event_feed_params(source="interception")
        ).json()
        detail = client.get(
            "/api/event-feed/interception/"
            f"{records['items'][0]['id']}/download"
        ).json()["entry"]
        history = client.get(
            "/api/event-feed", params=event_feed_params(source="api_call")
        ).json()
        disabled = client.put("/api/interception-test", json={"enabled": False})

    assert intercepted.status_code == 200, intercepted.text
    projected_interception = (
        '<status phase="start">running</status>'
        + INTERCEPTION_REPLY
        + '<status phase="end">completed</status>'
    )
    assert streamed_content(intercepted) == projected_interception
    assert RecordingFakeListChatModel.seen_messages == []
    assert len(records["items"]) == 1
    assert len(history["items"]) == 1
    assert {"request_body", "response_body"}.isdisjoint(history["items"][0])
    assert detail["request_raw_json"] == raw_json
    captured = json.loads(detail["model_request_raw_json"])
    assert [message["role"] for message in captured["messages"]] == ["system", "system", "user"]
    prompt_blocks = captured["messages"][0]["content"]
    prompt_text = "".join(block["text"] for block in prompt_blocks)
    assert prompt_text == "PRIMARY\n\nTODO\n\nCUSTOM"
    assert captured["messages"][1]["content"] == "CLIENT HEAD"
    assert captured["messages"][2]["content"] == "beforePRESETafter"
    tool_names = [item["function"]["name"] for item in captured["tools"]]
    assert "write_todos" in tool_names
    assert captured["model"]["type"].endswith("RecordingFakeListChatModel")
    assert disabled.json()["enabled"] is False
