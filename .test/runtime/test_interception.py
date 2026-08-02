from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import SecretStr

from agent_shell.runtime.interception import (
    INTERCEPTION_REPLY,
    InterceptionTestController,
    make_interception_middleware,
    serialize_model_request,
)


class SafeModelFixture:
    model_name = "provider-model"
    openai_api_base = "https://provider.example/v1"
    temperature = 0.2
    max_completion_tokens = 1024
    stop_sequences = ["END"]
    max_retries = 3
    api_key = SecretStr("provider-secret-must-not-leak")


@tool
def ping(message: str) -> str:
    """Return one test message."""

    return message


def request_fixture() -> SimpleNamespace:
    return SimpleNamespace(
        model=SafeModelFixture(),
        messages=[HumanMessage(content="question")],
        system_message=SystemMessage(content="agent rules"),
        tools=[ping],
        tool_choice="auto",
        response_format=None,
        model_settings={
            "metadata": SecretStr("request-secret-must-not-leak"),
            "api_key": "plain-secret-must-not-leak",
        },
    )


def test_model_request_serialization_is_complete_and_secret_safe() -> None:
    payload = serialize_model_request(request_fixture())
    wire = json.dumps(payload, ensure_ascii=False)

    assert [message["role"] for message in payload["messages"]] == [
        "system",
        "user",
    ]
    assert payload["model"] == {
        "type": f"{__name__}.SafeModelFixture",
        "name": "provider-model",
        "configuration": {
            "openai_api_base": "https://provider.example/v1",
            "temperature": 0.2,
            "max_completion_tokens": 1024,
            "stop_sequences": ["END"],
            "max_retries": 3,
        },
    }
    assert payload["tools"][0]["function"]["name"] == "ping"
    assert payload["tool_choice"] == "auto"
    assert payload["model_settings"] == {
        "metadata": "**********",
        "api_key": "[REDACTED]",
    }
    assert "provider-secret-must-not-leak" not in wire
    assert "request-secret-must-not-leak" not in wire
    assert "plain-secret-must-not-leak" not in wire


def test_tool_schema_conversion_failure_is_not_replaced_with_a_fake_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []
    provider_calls = []

    def fail_conversion(_tool):
        raise RuntimeError("tool schema conversion failed")

    monkeypatch.setattr(
        "langchain_core.utils.function_calling.convert_to_openai_tool",
        fail_conversion,
    )

    middleware = make_interception_middleware(captured.append)
    with pytest.raises(RuntimeError, match="tool schema conversion failed"):
        middleware.wrap_model_call(
            request_fixture(),
            lambda request: provider_calls.append(request),
        )

    assert captured == []
    assert provider_calls == []


def test_interception_middleware_captures_and_never_calls_provider_handler() -> None:
    captured = []
    middleware = make_interception_middleware(captured.append)

    def provider_handler(_request):
        raise AssertionError("Provider handler must not run")

    response = middleware.wrap_model_call(request_fixture(), provider_handler)

    assert len(captured) == 1
    assert response.result[0].content == INTERCEPTION_REPLY


def test_interception_switch_restores_the_persisted_setting() -> None:
    class SettingStore:
        enabled = False

        def snapshot(self) -> dict[str, bool]:
            return {
                "interception_enabled": self.enabled,
                "verbose_diagnostics": False,
            }

        def set_interception_enabled(self, enabled: bool) -> None:
            self.enabled = enabled

    store = SettingStore()
    first = InterceptionTestController(store)

    assert first.snapshot() == {"enabled": False}
    assert first.set_enabled(True) == {"enabled": True}
    assert InterceptionTestController(store).snapshot() == {"enabled": True}
    assert first.is_enabled() is True
