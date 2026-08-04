from __future__ import annotations

from .support import *

def test_selected_custom_middleware_executes_enabled_recipe_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    construction_count = tmp_path / "middleware-construction-count.txt"
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="middleware completed")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        middleware = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Runtime middleware",
                "middlewares": [
                    {
                        "name": "Disabled recipe",
                        "enabled": False,
                        "source": (
                            "raise RuntimeError('disabled recipe executed')\n"
                            "middleware = None\n"
                        ),
                    },
                    {
                        "name": "Email redaction",
                        "enabled": True,
                        "source": (
                            "from pathlib import Path\n"
                            f"counter = Path({str(construction_count)!r})\n"
                            "count = int(counter.read_text()) if counter.exists() else 0\n"
                            "counter.write_text(str(count + 1))\n"
                            "from langchain.agents.middleware import PIIMiddleware\n"
                            "middleware = [PIIMiddleware(\n"
                            "    'email', strategy='redact', apply_to_input=True\n"
                            ")]\n"
                        ),
                    },
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": middleware["id"]},
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
                    {"role": "user", "content": "Contact me at user@example.com"}
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert construction_count.read_text(encoding="utf-8") == "1"
    assert response.json()["choices"][0]["message"]["content"] == "middleware completed"
    human_message = next(
        message
        for message in ToolCallingFakeModel.seen_messages[0]
        if message.type == "human"
    )
    assert "user@example.com" not in human_message.text

def test_custom_middleware_construction_failure_is_safe_and_pre_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        middleware = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Broken runtime middleware",
                "middlewares": [
                    {
                        "name": "Broken recipe",
                        "enabled": True,
                        "source": (
                            "raise RuntimeError('private construction details')\n"
                            "middleware = None\n"
                        ),
                    }
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": middleware["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "custom_middleware_execution_failed"
    assert "private construction details" not in response.text
    assert ToolCallingFakeModel.seen_messages == []

def test_primary_duplicate_runtime_middleware_name_is_reported_pre_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Conflicting Primary middleware",
                "middlewares": [
                    {
                        "name": "Two runtime names",
                        "enabled": True,
                        "source": duplicate_runtime_middleware_source(),
                    }
                ],
            },
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": custom["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "agent_middleware_name_conflict"
    assert "Primary Agent" in error["message"]
    assert "shared_runtime_name" in error["message"]
    assert ToolCallingFakeModel.seen_messages == []

def test_subagent_duplicate_runtime_middleware_name_identifies_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    models = iter(
        [
            ToolCallingFakeModel(responses=[AIMessage(content="parent must not run")]),
            ToolCallingFakeModel(responses=[AIMessage(content="child must not run")]),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        custom = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Inherited conflicting middleware",
                "middlewares": [
                    {
                        "name": "Two inherited runtime names",
                        "enabled": True,
                        "source": duplicate_runtime_middleware_source(),
                    }
                ],
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Conflict delegation"},
        ).json()
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "Conflicted worker",
                name="conflicted_worker",
                description="Uses the inherited conflicting Middleware.",
            ),
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
                    {"type": "custom-middleware", "block_id": custom["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not run."}],
            },
        )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "agent_middleware_name_conflict"
    assert "Subagent conflicted_worker" in error["message"]
    assert "shared_runtime_name" in error["message"]
    assert ToolCallingFakeModel.seen_messages == []
