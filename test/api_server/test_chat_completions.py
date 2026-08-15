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
    assert message["content"] == "runtime reply"
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


def test_chat_materializes_condition_router_package_before_compiling_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_dir = (
        tmp_path
        / "data"
        / "templates"
        / "workflow"
        / "condition_router"
        / "always-run"
    )
    package_dir.mkdir(parents=True)
    (package_dir / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "family": "workflow-node",
                "adapter": "condition-router",
                "name": "Always run",
                "description": "Routes to the Agent branch.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "main.py").write_text(
        "def create_router(config):\n"
        "    async def route(state, context):\n"
        "        return {'activate': ['run'], 'update': {}}\n"
        "    return route\n",
        encoding="utf-8",
    )
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        selected = client.get(
            "/api/python-package-templates/condition-router"
        ).json()["catalog"][0]
        router = client.post(
            "/api/blocks/condition-router",
            json={
                "name": "Always run",
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": selected["main_source"],
                    "requirements_source": selected["requirements_source"],
                },
            },
        )
        assert router.status_code == 200, router.text
        workflow = create_workflow(client, name="Routed Workflow")
        graph = client.put(
            f"/api/workflows/{workflow['id']}/graph",
            json={
                "definition": {
                    "schema_version": 1,
                    "state_contract": "agent-shell.workflow.agent-invocations.v1",
                    "nodes": [
                        {"id": "start", "type": "start", "type_version": 1, "config": {}},
                        {
                            "id": "router",
                            "type": "condition-router",
                            "type_version": 1,
                            "config": {"condition_router_id": router.json()["id"]},
                        },
                        {
                            "id": "agent",
                            "type": "agent",
                            "type_version": 1,
                            "config": {"main_agent_id": main_agent["id"]},
                        },
                        {"id": "end", "type": "end", "type_version": 1, "config": {}},
                    ],
                    "edges": [
                        {"id": "start-router", "source": "start", "source_handle": "next", "target": "router", "target_handle": "in"},
                        {"id": "run", "source": "router", "source_handle": "branch", "target": "agent", "target_handle": "in", "branch_key": "run"},
                        {"id": "otherwise", "source": "router", "source_handle": "branch", "target": "end", "target_handle": "in", "branch_key": "otherwise"},
                        {"id": "agent-end", "source": "agent", "source_handle": "next", "target": "end", "target_handle": "in"},
                    ],
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

    assert graph.status_code == 200, graph.text
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "runtime reply"


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
    assert content == "runtime reply"
    assert chunks[-1]["choices"][0]["finish_reason"] == "unknown"


def test_workflow_agent_middleware_injects_frozen_client_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    InspectingFakeChatModel.seen_messages = []
    model = InspectingFakeChatModel(responses=["middleware reply"])
    write_middleware_template(
        tmp_path,
        "request-injection",
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
        selected = client.get(
            "/api/python-package-templates/middleware"
        ).json()["catalog"][0]
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Request message injection",
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": selected["main_source"],
                    "requirements_source": selected["requirements_source"],
                },
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
