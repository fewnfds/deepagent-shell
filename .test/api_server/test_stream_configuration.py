from __future__ import annotations

from .support import *

def test_selected_output_mode_wraps_the_same_timeline_for_both_transports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = attach_output_mode(
            client,
            create_main_agent(client),
            filter_mappings=[
                {"field": "lifecycle.phase", "value": "start"}
            ],
        )
        request = {
            "model": main_agent["name"],
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
        main_agent = create_main_agent(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "fail safely"}],
            },
        )
        failed_session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()
        streamed = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
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
        main_agent = create_main_agent(
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
                "model": main_agent["name"],
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

def test_global_interception_captures_final_prompt_tools_and_raw_request(
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
        main_agent = create_main_agent(client)
        write_automation_script(
            tmp_path,
            "capture-message-rewrite",
            "async def prepare(ctx):\n"
            "    tag = str(ctx.config.get('tag', ''))\n"
            "    replacement = str(ctx.config.get('replacement', ''))\n"
            "    for message in ctx.messages:\n"
            "        if message.get('role') == 'user':\n"
            "            message['content'] = message['content'].replace(tag, replacement)\n",
            config_schema=automation_config_schema(
                {"tag": "string", "replacement": "string"},
                required=("tag", "replacement"),
            ),
        )
        automation = {
            "hooks": [
                {
                    "plugin_id": "capture-message-rewrite",
                    "enabled": True,
                    "config": {
                        "tag": "|||agent_prompt|||",
                        "replacement": "PRESET",
                    },
                }
            ],
            "periodic": [],
        }
        prompt = client.post(
            "/api/blocks/system-prompt",
            json={"name": "Captured prompt", "system_prompt": "MAIN AGENT"},
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
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *[
                        item
                        for item in main_agent["capability_refs"]
                        if item["type"] != "output-mode"
                    ],
                    {"type": "system-prompt", "block_id": prompt["id"]},
                    {"type": "todo-list", "block_id": todo["id"]},
                    {"type": "custom-middleware", "block_id": custom["id"]},
                    {"type": "output-mode", "block_id": output_mode["id"]},
                ],
                "subagents": [],
                "automation": automation,
            },
        )
        assert updated.status_code == 200, updated.text
        armed = client.put("/api/interception-test", json={"enabled": True})
        assert armed.status_code == 200, armed.text
        request_payload = {
            "model": main_agent["name"],
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
    assert [message["role"] for message in captured["messages"]] == ["system"]
    prompt_blocks = captured["messages"][0]["content"]
    prompt_text = "".join(block["text"] for block in prompt_blocks)
    assert prompt_text == "MAIN AGENT\n\nTODO\n\nCUSTOM"
    tool_names = [item["function"]["name"] for item in captured["tools"]]
    assert "write_todos" in tool_names
    assert captured["model"]["type"].endswith("RecordingFakeListChatModel")
    assert disabled.json()["enabled"] is False
