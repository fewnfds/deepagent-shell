from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_shell.app import create_app
from agent_shell.capability_manifest import CAPABILITY_MANIFESTS
from support import ScopedAuthTestClient, configure_scope_tokens


PUBLIC_TYPES = tuple(manifest.type for manifest in CAPABILITY_MANIFESTS)
OVERRIDEABLE_TYPES = tuple(
    manifest.type for manifest in CAPABILITY_MANIFESTS if manifest.subagent_overrideable
)
REQUIRED_TYPES = tuple(
    manifest.type for manifest in CAPABILITY_MANIFESTS if manifest.required
)


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
OUTPUT_EVENT_TYPES = (
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "tool_error",
    "subagent",
    "custom",
    "lifecycle",
)


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    configure_scope_tokens(monkeypatch, tmp_path)
    return ScopedAuthTestClient(create_app())


def block_payload(capability_type: str, name: str) -> dict:
    payloads = {
        "model": {
            "name": name,
            "provider": "openai",
            "base_url": "https://example.invalid/v1",
            "credential": "reference-test-secret",
            "model": "fixture-model",
            "provider_settings": {
                "temperature": 0.7,
                "max_completion_tokens": 4096,
            },
            "tool_choice": None,
            "response_format": None,
            "model_settings": {},
        },
        "custom-tool": {"name": name, "tools": []},
        "custom-middleware": {"name": name, "middlewares": []},
        "output-mode": {
            "name": name,
            "filter_mode": "blocklist",
            "filter_mappings": [],
            "variable_encoding": "html",
            "event_templates": {
                event_type: {
                    "enabled": True,
                    "template": "{{message}}",
                }
                for event_type in OUTPUT_EVENT_TYPES
            },
        },
        "filesystem": {"name": name},
        "skill": {"name": name, "skills": ["fixture-skill"]},
        "system-prompt": {"name": name, "system_prompt": "Fixture prompt."},
        "subagent": {"name": name},
        "todo-list": {"name": name},
        "exception-retry": {
            "name": name,
            "strategy": "provider_native",
            "force_non_streaming": False,
            "max_retries": 2,
            "retry_on": [
                "transport_error",
                "timeout",
                "rate_limit",
                "server_error",
            ],
        },
    }
    return payloads[capability_type]


def create_blocks(client: TestClient, suffix: str, types=PUBLIC_TYPES) -> dict[str, dict]:
    blocks = {}
    for capability_type in types:
        response = client.post(
            f"/api/blocks/{capability_type}",
            json=block_payload(capability_type, f"{capability_type}-{suffix}"),
        )
        assert response.status_code == 200, response.text
        blocks[capability_type] = response.json()
    return blocks


def references(blocks: dict[str, dict], types=PUBLIC_TYPES) -> list[dict]:
    return [
        {"type": capability_type, "block_id": blocks[capability_type]["id"]}
        for capability_type in types
    ]


def write_custom_tool(tmp_path: Path, resource_name: str, tool_name: str) -> None:
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / f"{resource_name}.py").write_text(
        "from langchain_core.tools import tool\n"
        f"@tool({tool_name!r})\n"
        f"def {resource_name}(value: str) -> str:\n"
        '    """Test tool used by static assembly validation."""\n'
        "    return value\n",
        encoding="utf-8",
    )
