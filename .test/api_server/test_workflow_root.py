from __future__ import annotations

from pathlib import Path
import json
from langchain_core.messages import AIMessage

from .support import (
    ToolCallingFakeModel,
    create_main_agent,
    make_client,
    write_automation_script,
)


def test_workflow_is_chat_compatible_root_without_main_agent(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = {
        "public_id": "workflow-echo",
        "name": "Echo workflow",
        "description": "",
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "version": "1.0.0", "config": {}},
            {"id": "echo", "type": "builtin.tool.call", "version": "1.0.0", "config": {"tool_name": "echo", "arguments": {"text": "workflow reply"}}},
            {"id": "output", "type": "builtin.output.message", "version": "1.0.0", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "echo", "port": "messages"}},
            {"id": "e2", "source": {"node": "echo", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    created = client.post("/api/workflows", json=payload)
    assert created.status_code == 200, created.text

    models = client.get("/v1/models")
    assert models.status_code == 200
    assert "workflow-echo" in {item["id"] for item in models.json()["data"]}

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "workflow-echo",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "workflow reply"


def test_workflow_commit_emits_text_and_not_agent_message_content(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    output = tmp_path / "data" / "files" / "output"
    output.mkdir(parents=True)
    (output / "report.md").write_text("report body", encoding="utf-8")
    payload = {
        "public_id": "workflow-commit",
        "name": "Commit workflow",
        "description": "",
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "version": "1.0.0", "config": {}},
            {"id": "commit", "type": "builtin.tool.call", "version": "1.0.0", "config": {"tool_name": "commit", "arguments": {"path": "/output/report.md"}}},
            {"id": "output", "type": "builtin.output.message", "version": "1.0.0", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "commit", "port": "messages"}},
            {"id": "e2", "source": {"node": "commit", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    assert client.post("/api/workflows", json=payload).status_code == 200
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "workflow-commit",
            "messages": [{"role": "user", "content": "commit"}],
            "stream": False,
        },
    )
    assert response.status_code == 200, response.text
    artifacts = response.json()["agent_shell"]["artifact_commits"]
    assert artifacts[0]["content"] == "report body"
    assert response.json()["choices"][0]["message"]["content"] != "report body"


def test_workflow_commit_policy_transforms_stream_without_mutating_file(
    tmp_path: Path, monkeypatch
) -> None:
    write_automation_script(
        tmp_path,
        "commit-policy",
        "def wrap(path, text):\n"
        "    return '<artifact>' + text + '</artifact>'\n\n"
        "async def prepare(ctx):\n"
        "    ctx.configure_artifact_commit(transform=wrap, minimum_text_bytes=5)\n",
    )
    source = tmp_path / "data" / "files" / "output" / "report.md"
    source.parent.mkdir(parents=True)
    source.write_text("report body", encoding="utf-8")
    client = make_client(tmp_path, monkeypatch)
    workflow = {
        "public_id": "workflow-stream-artifact",
        "name": "Stream artifact",
        "preparation": [{"plugin_id": "commit-policy"}],
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "config": {}},
            {
                "id": "commit",
                "type": "builtin.tool.call",
                "config": {"tool_name": "commit", "arguments": {"path": "/output/report.md"}},
            },
            {"id": "output", "type": "builtin.output.message", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "commit", "port": "messages"}},
            {"id": "e2", "source": {"node": "commit", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    assert client.post("/api/workflows", json=workflow).status_code == 200

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "workflow-stream-artifact",
            "messages": [{"role": "user", "content": "commit"}],
            "stream": True,
        },
    )
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    artifact = next(item for item in chunks if item.get("agent_shell"))
    assert artifact["agent_shell"]["data"]["content"] == (
        "<artifact>report body</artifact>"
    )
    assert source.read_text(encoding="utf-8") == "report body"


def test_agent_root_commit_returns_status_to_agent_and_content_to_stream(
    tmp_path: Path, monkeypatch
) -> None:
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "commit",
                    "args": {"path": "/output/agent-report.md"},
                    "id": "commit-agent-report",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="agent completed"),
        ]
    )
    source = tmp_path / "data" / "files" / "output" / "agent-report.md"
    source.parent.mkdir(parents=True)
    source.write_text("agent report", encoding="utf-8")
    client = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "agent_shell.runtime.agent_builder._build_chat_model",
        lambda *_args: model,
    )
    agent = create_main_agent(client, public_id="agent-commit-root")
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": agent["public_id"],
            "messages": [{"role": "user", "content": "commit"}],
        },
    )
    assert response.status_code == 200, response.text
    artifact = response.json()["agent_shell"]["artifact_commits"][0]
    assert artifact["content"] == "agent report"
    tool_result = next(
        item
        for batch in model.seen_messages
        for item in batch
        if getattr(item, "type", "") == "tool"
    )
    assert "content" not in str(tool_result.content)


def test_auto_root_selects_workflow_before_target_execution(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = {
        "public_id": "workflow-routed",
        "name": "Routed workflow",
        "description": "",
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "version": "1.0.0", "config": {}},
            {"id": "echo", "type": "builtin.tool.call", "version": "1.0.0", "config": {"tool_name": "echo", "arguments": {"text": "routed"}}},
            {"id": "output", "type": "builtin.output.message", "version": "1.0.0", "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": {"node": "input", "port": "messages"}, "target": {"node": "echo", "port": "messages"}},
            {"id": "e2", "source": {"node": "echo", "port": "messages"}, "target": {"node": "output", "port": "messages"}},
        ],
    }
    assert client.post("/api/workflows", json=payload).status_code == 200
    auto = client.post(
        "/api/auto-roots",
        json={
            "public_id": "auto-default",
            "name": "Default route",
            "source": "def route(messages):\n    return {'kind': 'workflow', 'public_id': 'workflow-routed'}\n",
        },
    )
    assert auto.status_code == 200, auto.text
    assert "auto-default" in {item["id"] for item in client.get("/v1/models").json()["data"]}
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto-default",
            "messages": [{"role": "user", "content": "route me"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "routed"


def test_auto_routes_before_target_workflow_preparation(
    tmp_path: Path, monkeypatch
) -> None:
    write_automation_script(
        tmp_path,
        "prepare-workflow",
        "async def prepare(ctx):\n"
        "    ctx.messages.append({'role': 'assistant', 'content': 'prepared reply'})\n",
    )
    client = make_client(tmp_path, monkeypatch)
    workflow = {
        "public_id": "workflow-prepared",
        "name": "Prepared workflow",
        "preparation": [{"plugin_id": "prepare-workflow"}],
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "config": {}},
            {"id": "output", "type": "builtin.output.message", "config": {}},
        ],
        "edges": [
            {
                "id": "e1",
                "source": {"node": "input", "port": "messages"},
                "target": {"node": "output", "port": "messages"},
            }
        ],
    }
    assert client.post("/api/workflows", json=workflow).status_code == 200
    auto = {
        "public_id": "auto-prepared",
        "name": "Prepared route",
        "source": (
            "def route(messages):\n"
            "    assert messages[-1]['content'] == 'route me'\n"
            "    return {'kind': 'workflow', 'public_id': 'workflow-prepared'}\n"
        ),
    }
    assert client.post("/api/auto-roots", json=auto).status_code == 200

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "auto-prepared",
            "messages": [{"role": "user", "content": "route me"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "prepared reply"
