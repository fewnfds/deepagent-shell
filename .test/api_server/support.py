from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import os
import asyncio
import sqlite3
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage, ToolMessage
from starlette.requests import Request

from agent_shell.app import create_app
from agent_shell.api.api_server import ApiServerEventHub
from agent_shell.runtime.interception import INTERCEPTION_REPLY
from support import ScopedAuthTestClient, configure_scope_tokens


EVENT_FEED_TEST_WINDOW = {
    "started_at": "2000-01-01T00:00:00+00:00",
    "ended_at": "2100-01-01T00:00:00+00:00",
}


def event_feed_params(**filters: object) -> dict[str, object]:
    return {**EVENT_FEED_TEST_WINDOW, **filters}


def event_feed_query_pairs(*filters: tuple[str, object]) -> list[tuple[str, object]]:
    return [*EVENT_FEED_TEST_WINDOW.items(), *filters]


def add_api_event(
    client: TestClient,
    *,
    offset: int,
    body: str,
    status: str = "completed",
    response_body: str = '{"result":"ok"}',
) -> str:
    started = datetime.now(timezone.utc) + timedelta(seconds=offset)
    item = client.app.state.api_server_store.add_message_history(
        request_id=f"request-{offset}",
        model="published-model",
        agent_name="Published Primary",
        started_at=started.isoformat(timespec="milliseconds"),
        finished_at=(started + timedelta(milliseconds=10)).isoformat(
            timespec="milliseconds"
        ),
        status=status,
        request_body=body,
        response_body=response_body,
        response_content_type="application/json",
        http_status=200 if status == "completed" else 500,
        error_code=None if status == "completed" else "runtime_failed",
    )
    return str(item["id"])


class ToolCompatibleFakeListChatModel(FakeListChatModel):
    def _get_ls_params(self, stop=None, **kwargs):
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = "openai"
        return params

    def bind_tools(self, _tools, **_kwargs):
        return self


class RecordingFakeListChatModel(ToolCompatibleFakeListChatModel):
    seen_messages: ClassVar[list[list[object]]] = []

    async def _astream(self, messages, *args, **kwargs):
        self.seen_messages.append(list(messages))
        async for chunk in super()._astream(messages, *args, **kwargs):
            yield chunk


class ToolCallingFakeModel(FakeMessagesListChatModel):
    seen_messages: ClassVar[list[list[object]]] = []
    bound_tool_names: ClassVar[list[str]] = []
    bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    def _get_ls_params(self, stop=None, **kwargs):
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = "openai"
        return params

    def bind_tools(self, tools, **_kwargs):
        type(self).bound_tool_names = [tool.name for tool in tools]
        type(self).bound_tool_descriptions = {
            tool.name: tool.description for tool in tools
        }
        return self

    def _generate(self, messages, *args, **kwargs):
        type(self).seen_messages.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


@pytest.fixture(autouse=True)
def clean_agent_shell_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("AGENT_SHELL_"):
            monkeypatch.delenv(key, raising=False)


def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    configure_scope_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "agent_shell.runtime.agent_builder._build_chat_model",
        lambda _block, _credential, _http_clients: ToolCompatibleFakeListChatModel(
            responses=["runtime reply"]
        ),
    )
    return ScopedAuthTestClient(create_app())


def write_automation_script(
    tmp_path: Path,
    plugin_id: str,
    source: str,
    *,
    entrypoints: tuple[str, ...] = ("prepare",),
    config_schema: dict[str, object] | None = None,
) -> None:
    script_dir = (
        tmp_path / "data" / "resources" / "automation_scripts" / plugin_id
    )
    script_dir.mkdir(parents=True, exist_ok=True)
    (script_dir / "script.json").write_text(
        json.dumps(
            {
                "api_version": 3,
                "id": plugin_id,
                "name": plugin_id,
                "description": "Test automation plugin.",
                "entrypoints": list(entrypoints),
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                } if config_schema is None else config_schema,
            }
        ),
        encoding="utf-8",
    )
    (script_dir / "main.py").write_text(source, encoding="utf-8")


def automation_config_schema(
    fields: dict[str, str],
    *,
    required: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            name: {"type": field_type, "title": name}
            for name, field_type in fields.items()
        },
        "required": list(required),
        "additionalProperties": False,
    }


def create_primary(
    client: TestClient,
    *,
    provider_settings: dict[str, object] | None = None,
    model_request_settings: dict[str, object] | None = None,
    include_filesystem: bool = True,
) -> dict:
    model_payload = {
        "name": "Published model",
        "provider": "openai",
        "base_url": "https://provider.example/v1",
        "credential": "provider-test-secret",
        "model": "provider-model",
        "provider_settings": provider_settings or {},
        "tool_choice": None,
        "response_format": None,
        "model_settings": {},
        **(model_request_settings or {}),
    }
    model = client.post(
        "/api/blocks/model",
        json=model_payload,
    ).json()
    output_mode = client.post(
        "/api/blocks/output-mode",
        json=output_mode_payload("Published output", include_lifecycle=False),
    ).json()
    capability_refs = [{"type": "model", "block_id": model["id"]}]
    if include_filesystem:
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Published filesystem",
                "tool_configs": {
                    name: {"visible": False}
                    for name in (
                        "ls",
                        "write_file",
                        "edit_file",
                        "glob",
                        "grep",
                        "execute",
                    )
                },
            },
        ).json()
        capability_refs.append(
            {"type": "filesystem", "block_id": filesystem["id"]}
        )
    capability_refs.append(
        {"type": "output-mode", "block_id": output_mode["id"]}
    )
    response = client.post(
        "/api/primary-agents",
        json={
            "name": "Published Primary",
            "capability_refs": capability_refs,
            "subagents": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def subagent_payload(
    component_name: str,
    *,
    name: str = "worker",
    description: str = "Handles delegated work.",
    capability_overrides: list[dict[str, object]] | None = None,
    subagents: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "component_name": component_name,
        "name": name,
        "description": description,
        "settings": {
            "capability_overrides": capability_overrides or [],
            "subagents": subagents or [],
        },
    }


def output_mode_payload(
    name: str = "Visible timeline", *, include_lifecycle: bool = True
) -> dict:
    event_types = (
        "assistant_text",
        "reasoning",
        "tool_call",
        "tool_result",
        "tool_error",
        "subagent",
        "custom",
        "lifecycle",
    )
    templates = {
        event_type: {
            "enabled": False,
            "template": "{{message}}",
        }
        for event_type in event_types
    }
    templates["assistant_text"] = {
        "enabled": True,
        "template": "{{message}}",
    }
    templates["lifecycle"] = {
        "enabled": include_lifecycle,
        "template": '<status phase="{{phase}}">{{status}}</status>',
    }
    return {
        "name": name,
        "filter_mode": "blocklist",
        "filter_mappings": [],
        "variable_encoding": "html",
        "event_templates": templates,
    }


def attach_output_mode(
    client: TestClient,
    primary: dict,
    *,
    filter_mappings: list[dict[str, str]] | None = None,
) -> dict:
    output_payload = output_mode_payload()
    output_payload["filter_mappings"] = filter_mappings or []
    output_mode = client.post(
        "/api/blocks/output-mode", json=output_payload
    ).json()
    payload = {
        "name": primary["name"],
        "capability_refs": [
            *[
                item
                for item in primary["capability_refs"]
                if item["type"] != "output-mode"
            ],
            {"type": "output-mode", "block_id": output_mode["id"]},
        ],
        "subagents": primary["subagents"],
    }
    response = client.put(f"/api/primary-agents/{primary['id']}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def streamed_content_parts(response) -> list[str]:
    parts = []
    for line in response.text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        payload = json.loads(line.removeprefix("data: "))
        delta = payload.get("choices", [{}])[0].get("delta", {})
        if isinstance(delta.get("content"), str):
            parts.append(delta["content"])
    return parts


def streamed_content(response) -> str:
    return "".join(streamed_content_parts(response))


def capability_reference_id(primary: dict, capability_type: str) -> str:
    return next(
        item["block_id"]
        for item in primary["capability_refs"]
        if item["type"] == capability_type
    )


def replace_capability_reference(
    primary: dict, capability_type: str, block_id: str
) -> list[dict]:
    return [
        *[
            item
            for item in primary["capability_refs"]
            if item["type"] != capability_type
        ],
        {"type": capability_type, "block_id": block_id},
    ]


def duplicate_runtime_middleware_source() -> str:
    return (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class FirstRecipe(AgentMiddleware):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'shared_runtime_name'\n"
        "class SecondRecipe(AgentMiddleware):\n"
        "    @property\n"
        "    def name(self):\n"
        "        return 'shared_runtime_name'\n"
        "middleware = [FirstRecipe(), SecondRecipe()]\n"
    )
