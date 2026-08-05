from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest
from langchain_core.messages import AIMessage

from .support import (
    ToolCallingFakeModel,
    create_primary,
    make_client,
    write_automation_script,
)


def test_parallel_same_profile_invocations_have_isolated_plugin_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []

    call_ids = [f"call-{index}" for index in range(4)]
    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": f"delegated-{index}",
                            "subagent_type": "worker",
                        },
                        "id": call_id,
                        "type": "tool_call",
                    }
                    for index, call_id in enumerate(call_ids)
                ],
            ),
            AIMessage(content="all children complete"),
        ]
    )
    child_model = ChildModel(
        responses=[AIMessage(content=f"child-{index}") for index in range(4)]
    )

    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "invocation-workspace",
            "import asyncio\n"
            "import json\n"
            "from langchain.agents.middleware import AgentMiddleware\n"
            "class CaptureInvocation(AgentMiddleware):\n"
            "    def __init__(self, ctx):\n        self.ctx = ctx\n"
            "    async def abefore_agent(self, state, runtime):\n"
            "        invocation = runtime.context['agent_shell_invocation']\n"
            "        key = f\"{self.ctx.plugin['kind']}:{self.ctx.plugin['binding_index']}\"\n"
            "        scratch = invocation['workspaces'][key]\n"
            "        fixed = scratch / 'fixed.txt'\n"
            "        fixed.write_text(invocation['id'], encoding='utf-8')\n"
            "        async with self.ctx.vars['lock']:\n"
            "            self.ctx.vars['records'].append({\n"
            "                'id': invocation['id'],\n"
            "                'parent_id': invocation['parent_id'],\n"
            "                'cause': invocation['cause_tool_call_id'],\n"
            "                'agent_id': invocation['agent_id'],\n"
            "                'workspace': str(scratch),\n"
            "                'content': fixed.read_text(encoding='utf-8'),\n"
            "            })\n"
            "def create_middleware(ctx):\n    return CaptureInvocation(ctx)\n"
            "async def prepare(ctx):\n"
            "    ctx.vars.setdefault('lock', asyncio.Lock())\n"
            "    ctx.vars.setdefault('records', [])\n"
            "async def complete(ctx):\n"
            "    target = ctx.paths.plugin_dir / 'observed.json'\n"
            "    target.write_text(json.dumps(ctx.vars['records']), encoding='utf-8')\n",
            entrypoints=("prepare", "middleware", "complete"),
        )
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: (
                child_model if block["name"] == "Parallel child model" else parent_model
            ),
        )
        primary = create_primary(client)
        child_block = client.post(
            "/api/blocks/model",
            json={
                "name": "Parallel child model",
                "provider": "openai",
                "base_url": "https://provider.example/v1",
                "credential": "child-secret",
                "model": "child-model",
                "provider_settings": {},
                "tool_choice": None,
                "response_format": None,
                "model_settings": {},
            },
        ).json()
        subagent_response = client.post(
            "/api/subagents",
            json={
                "component_name": "Parallel worker profile",
                "name": "worker",
                "description": "Handles parallel delegated work.",
                "settings": {
                    "capability_overrides": [
                        {
                            "type": "model",
                            "mode": "replace",
                            "block_id": child_block["id"],
                        }
                    ],
                    "subagents": [],
                    "automation": {
                        "hooks": [
                            {
                                "plugin_id": "invocation-workspace",
                                "enabled": True,
                                "config": {},
                            }
                        ],
                        "periodic": [],
                    },
                },
            },
        )
        assert subagent_response.status_code == 200, subagent_response.text
        subagent = subagent_response.json()
        delegation = client.post(
            "/api/blocks/subagent", json={"name": "Parallel delegation"}
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *primary["capability_refs"],
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
                "messages": [{"role": "user", "content": "run four"}],
            },
        )
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 200, response.text
    observed_path = (
        tmp_path
        / "data"
        / "resources"
        / "automation_scripts"
        / "invocation-workspace"
        / "observed.json"
    )
    observed = json.loads(observed_path.read_text(encoding="utf-8"))
    assert len(observed) == 4
    assert {item["cause"] for item in observed} == set(call_ids)
    assert {item["agent_id"] for item in observed} == {subagent["id"]}
    assert len({item["id"] for item in observed}) == 4
    assert len({item["workspace"] for item in observed}) == 4
    assert len({item["parent_id"] for item in observed}) == 1
    assert all(item["content"] == item["id"] for item in observed)
    assert all("bindings\\hook-0\\invocations" in item["workspace"] for item in observed)
    assert all(not Path(item["workspace"]).exists() for item in observed)

    inputs = [
        item["data"]
        for item in session["runs"][0]["timeline"]
        if item["kind"] == "agent_input"
    ]
    root = next(item for item in inputs if item["agent_type"] == "primary")
    children = [item for item in inputs if item["agent_type"] == "subagent"]
    assert len(children) == 4
    assert {item["invocation_id"] for item in children} == {
        item["id"] for item in observed
    }
    assert {item["parent_invocation_id"] for item in children} == {
        root["invocation_id"]
    }
