from __future__ import annotations

from contextlib import closing
import json
import os
import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
)
from starlette.requests import Request

from agent_shell.app import create_app
from agent_shell.api.api_server import ApiServerEventHub
from support import API_KEY, ScopedAuthTestClient, configure_scope_tokens


EVENT_FEED_TEST_WINDOW = {
    "started_at": "2000-01-01T00:00:00+00:00",
    "ended_at": "2100-01-01T00:00:00+00:00",
}


def event_feed_params(**filters: object) -> dict[str, object]:
    return {**EVENT_FEED_TEST_WINDOW, **filters}


def event_feed_query_pairs(*filters: tuple[str, object]) -> list[tuple[str, object]]:
    return [*EVENT_FEED_TEST_WINDOW.items(), *filters]


class ToolCompatibleFakeListChatModel(FakeListChatModel):
    def _get_ls_params(self, stop=None, **kwargs):
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = "openai"
        return params

    def bind_tools(self, _tools, **_kwargs):
        return self


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


def write_middleware_package(
    tmp_path: Path,
    package_id: str,
    source: str,
    *,
    config_schema: dict[str, object] | None = None,
    requirements: tuple[str, ...] = (),
) -> None:
    package_dir = (
        tmp_path / "data" / "resources" / "custom_middlewares" / package_id
    )
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "middleware.json").write_text(
        json.dumps(
            {
                "api_version": 1,
                "id": package_id,
                "name": package_id,
                "description": "Test custom Middleware package.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                } if config_schema is None else config_schema,
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "main.py").write_text(source, encoding="utf-8")
    if requirements:
        (package_dir / "requirements.txt").write_text(
            "\n".join(requirements) + "\n",
            encoding="utf-8",
        )


def middleware_config_schema(
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


def create_main_agent(
    client: TestClient,
    *,
    provider_settings: dict[str, object] | None = None,
    model_request_settings: dict[str, object] | None = None,
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
    capability_refs.append(
        {"type": "output-mode", "block_id": output_mode["id"]}
    )
    response = client.post(
        "/api/main-agents",
        json={
            "name": "Published Main Agent",
            "capability_refs": capability_refs,
            "subagents": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_workflow(
    client: TestClient,
    *,
    name: str | None = None,
    enabled: bool = True,
    filesystem_id: str | None = None,
) -> dict:
    workflow_name = name or "Test Workflow"
    if filesystem_id is None:
        filesystem_response = client.post(
            "/api/blocks/filesystem",
            json={"name": f"{workflow_name} filesystem"},
        )
        assert filesystem_response.status_code == 200, filesystem_response.text
        filesystem_id = filesystem_response.json()["id"]
    response = client.post(
        "/api/workflows",
        json={
            "name": workflow_name,
            "description": "Test Workflow.",
            "filesystem_id": filesystem_id,
            "enabled": enabled,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def save_linear_workflow_graph(
    client: TestClient,
    workflow: dict,
    main_agent: dict,
) -> dict:
    document = {
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
            "edges": [
                {
                    "id": "start-agent",
                    "source": "start",
                    "source_handle": "next",
                    "target": "agent",
                    "target_handle": "in",
                },
                {
                    "id": "agent-end",
                    "source": "agent",
                    "source_handle": "next",
                    "target": "end",
                    "target_handle": "in",
                },
            ],
        },
        "layout": {
            "nodes": {
                "start": {"x": 80, "y": 160},
                "agent": {"x": 360, "y": 160},
                "end": {"x": 640, "y": 160},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }
    response = client.put(
        f"/api/workflows/{workflow['id']}/graph",
        json=document,
    )
    assert response.status_code == 200, response.text
    return response.json()


def subagent_payload(
    component_name: str,
    *,
    name: str = "worker",
    description: str = "Handles delegated work.",
    capability_overrides: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "component_name": component_name,
        "name": name,
        "description": description,
        "settings": {
            "capability_overrides": capability_overrides or [],
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


def capability_reference_id(main_agent: dict, capability_type: str) -> str:
    return next(
        item["block_id"]
        for item in main_agent["capability_refs"]
        if item["type"] == capability_type
    )
