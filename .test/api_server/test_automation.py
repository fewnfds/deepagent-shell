from __future__ import annotations

import base64

from agent_shell.automation.dependencies import dependency_state_path

from .support import *


def automation_config(
    plugin_id: str,
    *,
    interval: float | None = None,
) -> dict[str, object]:
    binding = {"plugin_id": plugin_id, "enabled": True, "config": {}}
    return {
        "hooks": [binding],
        "periodic": (
            [{**binding, "interval_seconds": interval}]
            if interval is not None
            else []
        ),
    }


def main_agent_update(main_agent: dict, automation: dict[str, object]) -> dict[str, object]:
    return {
        "name": main_agent["name"],
        "capability_refs": main_agent["capability_refs"],
        "subagents": main_agent["subagents"],
        "automation": automation,
    }


def test_plugin_catalog_direct_binding_and_old_workflow_routes_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "open-plugin",
            "async def prepare(ctx):\n    ctx.vars['seen'] = True\n"
            "async def lifecycle(ctx):\n    return None\n",
            entrypoints=("prepare", "lifecycle"),
        )
        catalog = client.get("/api/automation/plugins")
        main_agent = create_main_agent(client)
        attached = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(
                main_agent,
                automation_config("open-plugin", interval=2),
            ),
        )
        stored = client.get(f"/api/main-agents/{main_agent['id']}")
        old_catalog = client.get("/api/automation/scripts")
        old_hook = client.post(
            "/api/automation/hook-workflow",
            json={"name": "Removed", "hooks": {}},
        )
        old_lifecycle = client.post(
            "/api/automation/lifecycle-workflow",
            json={"name": "Removed", "interval_seconds": 2, "nodes": []},
        )
        old_draft = client.post(
            "/api/validation/draft",
            json={
                "target": {"kind": "automation", "type": "hook-workflow"},
                "payload": {},
            },
        )

    assert catalog.status_code == 200
    assert [item["id"] for item in catalog.json()["catalog"]] == ["open-plugin"]
    assert catalog.json()["catalog"][0]["entrypoints"] == [
        "prepare",
        "lifecycle",
    ]
    assert attached.status_code == 200, attached.text
    assert stored.json()["automation"] == automation_config(
        "open-plugin", interval=2
    )
    assert old_catalog.status_code == 404
    assert old_hook.status_code == 404
    assert old_lifecycle.status_code == 404
    assert old_draft.status_code == 422


def test_repository_validation_rechecks_changed_plugin_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "mutable-plugin",
            "async def prepare(ctx):\n    return None\n",
        )
        main_agent = create_main_agent(client)
        attached = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(main_agent, automation_config("mutable-plugin")),
        )
        stopped = client.post("/api/api-server/stop")
        script_path = (
            tmp_path
            / "data"
            / "resources"
            / "automation_scripts"
            / "mutable-plugin"
            / "main.py"
        )
        script_path.unlink()
        started = client.post("/api/api-server/start")

    assert attached.status_code == 200, attached.text
    assert stopped.status_code == 200
    assert started.status_code == 422
    issues = started.json()["detail"]["validation"]["issues"]
    assert any(
        issue["owner_id"] == main_agent["id"]
        and issue["code"] == "automation.plugin_invalid"
        for issue in issues
    )


def test_binding_requires_current_plugin_dependency_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "image-reader",
            "async def prepare(ctx):\n    return None\n",
        )
        plugin = (
            tmp_path
            / "data"
            / "resources"
            / "automation_scripts"
            / "image-reader"
        )
        (plugin / "requirements.txt").write_text(
            "Pillow>=11,<13\n", encoding="utf-8"
        )
        catalog = client.get("/api/automation/plugins").json()["catalog"]
        main_agent = create_main_agent(client)
        payload = main_agent_update(main_agent, automation_config("image-reader"))
        pending = client.put(
            f"/api/main-agents/{main_agent['id']}", json=payload
        )
        state_path = dependency_state_path(tmp_path / "runtime")
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "platform": "windows-x64",
                    "status": "ready",
                    "plugins": {
                        "image-reader": {
                            "requirements_fingerprint": catalog[0][
                                "requirements_fingerprint"
                            ],
                            "status": "ready",
                            "error_code": "",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        ready = client.put(
            f"/api/main-agents/{main_agent['id']}", json=payload
        )

    assert catalog[0]["dependency_status"] == "restart_required"
    assert pending.status_code == 422
    assert pending.json()["detail"]["validation"]["issues"][0]["code"] == (
        "automation.plugin_dependencies_restart_required"
    )
    assert ready.status_code == 200, ready.text


def test_native_middleware_hook_shares_prepare_context_and_original_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "native-hook.txt"
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "native-hook",
            "from pathlib import Path\n"
            "from langchain.agents.middleware import AgentMiddleware\n"
            "class NativeHook(AgentMiddleware):\n"
            "    def __init__(self, ctx):\n        self.ctx = ctx\n"
            "    async def awrap_model_call(self, request, handler):\n"
            "        original = self.ctx.request.messages[0]['content']\n"
            "        shared = self.ctx.vars.get('prepared')\n"
            "        Path(self.ctx.config['marker']).write_text(f'{original}|{shared}')\n"
            "        return await handler(request)\n"
            "def create_middleware(ctx):\n    return NativeHook(ctx)\n"
            "async def prepare(ctx):\n"
            "    ctx.vars['prepared'] = True\n",
            entrypoints=("middleware", "prepare"),
            config_schema=automation_config_schema(
                {"marker": "string"}, required=("marker",)
            ),
        )
        main_agent = create_main_agent(client)
        attached = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(
                main_agent,
                {
                    "hooks": [{
                        "plugin_id": "native-hook",
                        "enabled": True,
                        "config": {"marker": str(marker)},
                    }],
                    "periodic": [],
                },
            ),
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "original"}],
            },
        )

    assert attached.status_code == 200, attached.text
    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "runtime reply"
    assert marker.read_text(encoding="utf-8") == "original|True"


def test_binding_config_must_satisfy_the_plugin_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "schema-plugin",
            "async def prepare(ctx):\n    return None\n",
            config_schema=automation_config_schema(
                {"transform_source": "string"},
                required=("transform_source",),
            ),
        )
        main_agent = create_main_agent(client)
        response = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(
                main_agent,
                {
                    "hooks": [{
                        "plugin_id": "schema-plugin",
                        "enabled": True,
                        "config": {"transform_source": 42},
                    }],
                    "periodic": [],
                },
            ),
        )

    assert response.status_code == 422
    issue = response.json()["detail"]["validation"]["issues"][0]
    assert issue["code"] == "automation.plugin_config_invalid"
    assert issue["path"].endswith(".config.transform_source")
    assert issue["message_args"] == {
        "plugin_id": "schema-plugin",
        "keyword": "type",
    }


def test_python_plugin_config_must_parse_before_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "python-config-plugin",
            "async def prepare(ctx):\n    return None\n",
            config_schema={
                "type": "object",
                "properties": {
                    "transform_source": {
                        "type": "string",
                        "title": "Transform",
                        "format": "python",
                        "contentMediaType": "text/x-python",
                        "default": "",
                    },
                },
                "additionalProperties": False,
            },
        )
        main_agent = create_main_agent(client)
        response = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(
                main_agent,
                {
                    "hooks": [{
                        "plugin_id": "python-config-plugin",
                        "enabled": True,
                        "config": {"transform_source": "async def broken(:\n"},
                    }],
                    "periodic": [],
                },
            ),
        )

    assert response.status_code == 422
    issue = response.json()["detail"]["validation"]["issues"][0]
    assert issue["code"] == "automation.plugin_config_invalid"
    assert issue["message_args"] == {
        "plugin_id": "python-config-plugin",
        "keyword": "format",
    }


def test_prepare_can_relay_normalized_multimodal_message_to_langchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = RecordingFakeListChatModel(responses=["multimodal accepted"])
    RecordingFakeListChatModel.seen_messages = []
    image = base64.b64encode(b"image-bytes").decode("ascii")
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        write_automation_script(
            tmp_path,
            "relay-for-test",
            "async def prepare(ctx):\n    ctx.messages.extend(ctx.request.messages)\n",
        )
        main_agent = create_main_agent(client, include_filesystem=False)
        attached = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json=main_agent_update(main_agent, automation_config("relay-for-test")),
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "inspect"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image}"
                                },
                            },
                        ],
                    }
                ],
            },
        )

    assert attached.status_code == 200, attached.text
    assert response.status_code == 200, response.text
    human = next(
        message
        for message in RecordingFakeListChatModel.seen_messages[0]
        if message.type == "human"
    )
    assert [block["type"] for block in human.content_blocks] == ["text", "image"]
    assert human.content_blocks[1]["base64"] == image
    assert human.content_blocks[1]["mime_type"] == "image/png"
