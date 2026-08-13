from __future__ import annotations

import asyncio
from typing import ClassVar

from agent_shell.api import api_server

from .support import *


class InspectingFakeChatModel(ToolCompatibleFakeListChatModel):
    seen_messages: ClassVar[list[list[object]]] = []

    def _call(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_messages.append(list(messages))
        return super()._call(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_messages.append(list(messages))
        async for chunk in super()._astream(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        ):
            yield chunk


def test_models_publish_only_enabled_workflows_and_chat_runs_current_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        workflow = create_workflow(client, name="Published Workflow")
        save_linear_workflow_graph(client, workflow, main_agent)
        create_workflow(client, name="Disabled Workflow", enabled=False)

        models = client.get("/v1/models")
        workflow_reply = client.post(
            "/v1/chat/completions",
            json={
                "model": workflow["name"],
                "messages": [{"role": "user", "content": "run"}],
            },
        )
        main_agent_name_reply = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "run"}],
            },
        )
        main_agent_id_reply = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["id"],
                "messages": [{"role": "user", "content": "run"}],
            },
        )

    assert models.status_code == 200
    assert [item["id"] for item in models.json()["data"]] == [workflow["name"]]
    assert workflow_reply.status_code == 200, workflow_reply.text
    message = workflow_reply.json()["choices"][0]["message"]
    assert message["role"] == "assistant"
    assert message["content"].startswith("running")
    assert "runtime reply" in message["content"]
    assert message["content"].endswith("completed")
    for response in (main_agent_name_reply, main_agent_id_reply):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "model_not_found"


def test_chat_rejects_an_incomplete_saved_workflow_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        workflow = create_workflow(client, name="Incomplete Workflow")
        saved = client.put(
            f"/api/workflows/{workflow['id']}/graph",
            json={
                "definition": {
                    "schema_version": 1,
                    "state_contract": "agent-shell.workflow.agent-invocations.v1",
                    "nodes": [
                        {"id": "start", "type": "start", "type_version": 1, "config": {}},
                        {
                            "id": "agent",
                            "type": "agent",
                            "type_version": 1,
                            "config": {"main_agent_id": main_agent["id"]},
                        },
                        {"id": "end", "type": "end", "type_version": 1, "config": {}},
                    ],
                    "edges": [],
                },
                "layout": {"nodes": {}, "viewport": {"x": 0, "y": 0, "zoom": 1}},
            },
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": workflow["name"],
                "messages": [{"role": "user", "content": "run"}],
            },
        )

    assert saved.status_code == 200, saved.text
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "workflow.node_cannot_reach_end"


def test_chat_completion_stream_runs_current_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        workflow = create_workflow(client, name="Streaming Workflow")
        save_linear_workflow_graph(client, workflow, main_agent)
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "model": workflow["name"],
                "messages": [{"role": "user", "content": "run"}],
                "stream": True,
            },
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line.removeprefix("data: ")) for line in lines[:-1]]
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    content = "".join(
        chunk["choices"][0]["delta"].get("content", "") for chunk in chunks
    )
    assert content.startswith("running")
    assert "runtime reply" in content
    assert content.endswith("completed")
    assert chunks[-1]["choices"][0]["finish_reason"] == "unknown"


def test_workflow_agent_middleware_injects_frozen_client_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    InspectingFakeChatModel.seen_messages = []
    model = InspectingFakeChatModel(responses=["middleware reply"])
    write_middleware_package(
        tmp_path,
        "inject-request",
        "from langchain.agents.middleware import AgentMiddleware\n"
        "from langchain_core.messages import HumanMessage\n"
        "class InjectRequest(AgentMiddleware):\n"
        "    async def abefore_agent(self, state, runtime):\n"
        "        content = runtime.context.messages[-1]['content']\n"
        "        return {'messages': [HumanMessage(content=content)]}\n"
        "def create_middleware(config, agent):\n"
        "    return InjectRequest()\n",
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Request message injection",
                "middlewares": [
                    {
                        "package_id": "inject-request",
                        "enabled": True,
                        "config": {},
                    }
                ],
            },
        )
        assert custom.status_code == 200, custom.text
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {"type": "custom-middleware", "block_id": custom.json()["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        workflow = create_workflow(client, name="Middleware Workflow")
        save_linear_workflow_graph(client, workflow, updated.json())
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": workflow["name"],
                "messages": [{"role": "user", "content": "frozen client input"}],
            },
        )

    assert response.status_code == 200, response.text
    assert "middleware reply" in response.json()["choices"][0]["message"]["content"]
    assert [
        message.content
        for message in InspectingFakeChatModel.seen_messages[0]
        if message.type != "system"
    ] == ["frozen client input"]


def test_chat_completion_body_limit_runs_before_workflow_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        workflow = create_workflow(client)
        monkeypatch.setattr(api_server, "MAX_CHAT_COMPLETION_BODY_BYTES", 128)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": workflow["name"],
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
