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
    "todo-list",
    "custom-tool",
    "skill",
    "custom-middleware",
    "output-mode",
    "exception-retry",
    "prompt-preset",
    "subagent",
)

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
        "filter_mode": "blocklist",
        "filter_mappings": [],
        "variable_encoding": "html",
        "event_templates": {
            event_type: {
                "enabled": event_type != "reasoning",
                "template": "{{message}}",
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
                "middlewares": [
                    {
                        "name": "Tool retry",
                        "enabled": True,
                        "source": (
                            "from langchain.agents.middleware import ToolRetryMiddleware\n\n"
                            "middleware = ToolRetryMiddleware(max_retries=3)"
                        ),
                    },
                    {
                        "name": "Disabled draft",
                        "enabled": False,
                        "source": "middleware = object()",
                    },
                ],
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
        ("skill", {"name": "Writing skills", "skills": ["outline"]}),
        (
            "system-prompt",
            {"name": "Concise", "system_prompt": "Be concise."},
        ),
        ("subagent", {"name": "Delegation"}),
        (
            "todo-list",
            {
                "name": "Complex task planning",
                "system_prompt_override": "Track complex work and update each completed step.",
                "tool_description_override": None,
            },
        ),
        (
            "prompt-preset",
            {
                "name": "Writing startup",
                "tag_replacements": [],
                "startup_messages": [
                    {
                        "role": "user",
                        "content_template": "Begin work.",
                    }
                ],
            },
        ),
    ]
