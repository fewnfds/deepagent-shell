from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from agent_shell.app import create_app
from support import ScopedAuthTestClient, configure_scope_tokens


PUBLIC_TYPES = (
    "model",
    "system-prompt",
    "filesystem",
    "filesystem-permissions",
    "todo-list",
    "custom-tool",
    "skill",
    "custom-middleware",
    "output-mode",
    "exception-retry",
    "subagent",
    "summarization",
    "prompt-caching",
)


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


def model_payload(name: str = "Local model") -> dict:
    return {
        "name": name,
        "provider": "openai",
        "base_url": "http://127.0.0.1:8000/v1",
        "credential": "test-secret",
        "model": "test-model",
        "provider_settings": {
            "temperature": 0,
            "max_completion_tokens": 4096,
            "stream_usage": False,
            "streaming": True,
            "stop_sequences": ["END"],
        },
        "tool_choice": "auto",
        "response_format": {
            "title": "Answer",
            "description": "Structured answer returned by the model.",
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        "model_settings": {"parallel_tool_calls": False},
    }


def output_mode_payload(name: str = "Development timeline") -> dict:
    return {
        "name": name,
        "event_outputs": {
            event_type: {
                "enabled": event_type != "reasoning",
                "output_source": 'def output(event):\n    return event["message"]\n',
            }
            for event_type in OUTPUT_EVENT_TYPES
        },
    }


def block_cases(tmp_path: Path) -> list[tuple[str, dict]]:
    mapped = tmp_path / "mapped"
    mapped.mkdir()
    return [
        ("model", model_payload()),
        ("custom-tool", {"name": "Writing tools", "tools": ["word_count"]}),
        (
            "custom-middleware",
            {
                "name": "Reliability middleware",
            },
        ),
        ("output-mode", output_mode_payload()),
        (
            "exception-retry",
            {
                "name": "Reliable completion",
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
        ),
        (
            "filesystem",
            {
                "name": "Workspace",
                "mapped_directories": [
                    {"virtual_path": "/workspace/", "local_path": str(mapped)}
                ],
                "system_prompt_override": "Use only the configured workspace.",
                "tool_token_limit_before_evict": 4096,
                "tool_configs": {
                    "read_file": {"visible": True},
                    "write_file": {"visible": True},
                },
            },
        ),
        (
            "filesystem-permissions",
            {
                "name": "Workspace permissions",
                "permissions": [
                    {"path": "/workspace/**", "permission": "read-only"}
                ],
                "system_prompt_override": {"value": "Review files without changing them."},
                "tool_overrides": {
                    "write_file": {
                        "visible": False,
                        "description_override": None,
                    }
                },
            },
        ),
        ("skill", {"name": "Writing skills", "skills": ["outline"]}),
        (
            "system-prompt",
            {"name": "Concise", "system_prompt": "Be concise."},
        ),
        ("subagent", {"name": "Delegation"}),
        (
            "summarization",
            {
                "name": "Long-context summarization",
                "trigger": {"type": "tokens", "value": 120000},
                "keep": {"type": "messages", "value": 8},
            },
        ),
        (
            "prompt-caching",
            {
                "name": "One-hour prompt cache",
                "ttl": "1h",
                "min_messages_to_cache": 4,
            },
        ),
        (
            "todo-list",
            {
                "name": "Complex task planning",
                "system_prompt_override": "Track complex work and update each completed step.",
                "tool_description_override": None,
            },
        ),
    ]
