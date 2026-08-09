from __future__ import annotations

from langchain_core.messages import AIMessage

from .support import *


def test_shared_vars_flow_from_main_to_direct_subagent_and_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "task",
                    "args": {
                        "description": "Run the shared-state probe.",
                        "subagent_type": "state_worker",
                    },
                    "id": "call-state-worker",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="shared state returned"),
        ]
    )
    child_model = ToolCallingFakeModel(
        responses=[AIMessage(content="child complete")]
    )
    child_marker = tmp_path / "child-shared-state.txt"
    parent_marker = tmp_path / "parent-shared-state.txt"

    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "shared-state-probe",
            "from pathlib import Path\n"
            "from langchain.agents.middleware import AgentMiddleware\n"
            "class SharedStateProbe(AgentMiddleware):\n"
            "    def __init__(self, ctx):\n        self.ctx = ctx\n"
            "    async def abefore_agent(self, state, runtime):\n"
            "        shared = state.get('shared_vars', {})\n"
            "        if self.ctx.agent['type'] == 'main_agent':\n"
            "            return {'shared_vars': {'parent_seed': 'ready'}}\n"
            "        Path(self.ctx.config['child_marker']).write_text(\n"
            "            str(shared.get('parent_seed')), encoding='utf-8'\n"
            "        )\n"
            "        return {'shared_vars': {'child_result': 'complete'}}\n"
            "    async def abefore_model(self, state, runtime):\n"
            "        if self.ctx.agent['type'] != 'main_agent':\n"
            "            return None\n"
            "        result = state.get('shared_vars', {}).get('child_result')\n"
            "        if result is not None:\n"
            "            Path(self.ctx.config['parent_marker']).write_text(\n"
            "                str(result), encoding='utf-8'\n"
            "            )\n"
            "        return None\n"
            "def create_middleware(ctx):\n    return SharedStateProbe(ctx)\n",
            entrypoints=("middleware",),
            config_schema=automation_config_schema(
                {
                    "child_marker": "string",
                    "parent_marker": "string",
                },
                required=("child_marker", "parent_marker"),
            ),
        )
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda block, _credential, *_args: (
                child_model
                if block["name"] == "Shared-state child model"
                else parent_model
            ),
        )
        main_agent = create_main_agent(client)
        child_model_block = client.post(
            "/api/blocks/model",
            json={
                "name": "Shared-state child model",
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
        binding = {
            "plugin_id": "shared-state-probe",
            "enabled": True,
            "config": {
                "child_marker": str(child_marker),
                "parent_marker": str(parent_marker),
            },
        }
        child_payload = subagent_payload(
            "Shared-state worker",
            name="state_worker",
            capability_overrides=[{
                "type": "model",
                "mode": "replace",
                "block_id": child_model_block["id"],
            }],
        )
        child_payload["settings"]["automation"] = {
            "hooks": [binding],
            "periodic": [],
        }
        child_response = client.post("/api/subagents", json=child_payload)
        assert child_response.status_code == 200, child_response.text
        child = child_response.json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Shared-state delegation"},
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": child["id"]}],
                "automation": {"hooks": [binding], "periodic": []},
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Run the probe."}],
            },
        )

    assert response.status_code == 200, response.text
    assert child_marker.read_text(encoding="utf-8") == "ready"
    assert parent_marker.read_text(encoding="utf-8") == "complete"
