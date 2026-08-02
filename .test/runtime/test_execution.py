from __future__ import annotations

import importlib
import inspect

from .support import *
from .support import _build_chat_model
from langchain_core.messages import AIMessageChunk
from agent_shell.model_provider_contracts import _SETTINGS_BY_PROVIDER
from agent_shell.provider_http import PROVIDER_HTTP_TIMEOUT
from agent_shell.provider_integrations import bundled_provider_integrations
from agent_shell.runtime import agent_builder
from agent_shell.runtime.model_response import ModelResponse, finish_reason_category
from agent_shell.runtime.output_stream import OutputEvent
from agent_shell.runtime.session_recording import AgentRunCapture

def test_model_builder_never_reads_an_unrelated_environment_key(
    monkeypatch, provider_http_clients
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret-that-must-not-be-used")
    model = _build_chat_model(
        {
            "provider": "openai",
            "model": "local",
            "base_url": "http://127.0.0.1:8000/v1",
            "provider_settings": {},
        },
        None,
        provider_http_clients,
    )

    assert model.openai_api_key.get_secret_value() == "agent-shell-no-credential"


def test_deepseek_provider_adapter_preserves_streamed_reasoning_blocks(
    provider_http_clients,
) -> None:
    model = _build_chat_model(
        {
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "base_url": "https://gateway.example.invalid/v1",
            "provider_settings": {},
        },
        "provider-secret",
        provider_http_clients,
    )

    generation = model._convert_chunk_to_generation_chunk(
        {
            "id": "response-1",
            "model": "deepseek-reasoner",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "reasoning_content": "thought"},
                    "finish_reason": None,
                }
            ],
        },
        AIMessageChunk,
        None,
    )

    assert type(model).__name__ == "ChatDeepSeek"
    assert generation is not None
    assert generation.message.content_blocks == [
        {"type": "reasoning", "reasoning": "thought"}
    ]
    assert generation.message.response_metadata["model_provider"] == "deepseek"


@pytest.mark.parametrize(
    ("provider", "settings", "credential"),
    [
        (
            "openai",
            {"max_completion_tokens": 100, "stop_sequences": ["END"], "reasoning_effort": "high"},
            "secret",
        ),
        (
            "deepseek",
            {"max_tokens": 100, "stop_sequences": ["END"], "reasoning_effort": "high"},
            "secret",
        ),
        (
            "anthropic",
            {"max_tokens_to_sample": 100, "stop": ["END"], "effort": "high"},
            "secret",
        ),
        (
            "google_genai",
            {"max_tokens": 100, "request_timeout": 4, "retries": 3, "thinking_level": "high"},
            "secret",
        ),
        (
            "google_vertexai",
            {"max_tokens": 100, "timeout": 4, "max_retries": 3},
            None,
        ),
        (
            "xai",
            {
                "max_tokens": 100,
                "stop_sequences": ["END"],
                "reasoning_effort": "high",
                "timeout": 4,
            },
            "secret",
        ),
    ],
)
def test_model_builder_passes_native_provider_fields_unchanged(
    monkeypatch,
    provider: str,
    settings: dict,
    credential: str | None,
    provider_http_clients,
) -> None:
    captured = {}

    def fake_init_chat_model(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(agent_builder, "init_chat_model", fake_init_chat_model)
    block = {
        "provider": provider,
        "model": "provider-model",
        "base_url": "https://provider.example.invalid/v1",
        "provider_settings": settings,
    }

    _build_chat_model(block, credential, provider_http_clients)

    assert captured["model"] == "provider-model"
    assert captured["model_provider"] == provider
    assert captured["base_url"] == "https://provider.example.invalid/v1"
    assert {key: captured[key] for key in settings} == settings
    if provider == "google_vertexai":
        assert "api_key" not in captured
    else:
        assert captured["api_key"].get_secret_value() == credential
    if provider in {"deepseek", "openai", "xai"}:
        assert captured["http_client"] is provider_http_clients.sync_client
        assert captured["http_async_client"] is provider_http_clients.async_client
        assert captured["default_headers"] == {"User-Agent": "Agent-Shell/0.2.0"}
        assert captured["timeout"] == settings.get("timeout", PROVIDER_HTTP_TIMEOUT)
    else:
        assert "http_client" not in captured
        assert "http_async_client" not in captured
        assert "default_headers" not in captured


def test_provider_setting_contracts_use_current_official_constructor_names() -> None:
    for integration in bundled_provider_integrations():
        module = importlib.import_module(integration.module)
        model_type = getattr(module, integration.class_name)
        constructor_fields = inspect.signature(model_type).parameters
        contract_fields = _SETTINGS_BY_PROVIDER[integration.provider].model_fields

        assert contract_fields.keys() <= constructor_fields.keys(), integration.provider


def test_model_builder_requires_vertex_application_default_credentials(
    monkeypatch, provider_http_clients
) -> None:
    monkeypatch.setattr(agent_builder, "init_chat_model", lambda **kwargs: kwargs)

    with pytest.raises(AgentRuntimeError) as vertex_credential:
        _build_chat_model(
            {
                "provider": "google_vertexai",
                "model": "gemini",
                "base_url": "https://aiplatform.googleapis.com",
                "provider_settings": {},
            },
            "api-key-is-not-google-credentials",
            provider_http_clients,
        )

    assert vertex_credential.value.code == "model_configuration_invalid"


def test_session_capture_persists_only_explicit_workflow_fields() -> None:
    capture = AgentRunCapture()
    capture.model_request(
        {
            "agent_type": "context_worker",
            "agent_name": "Worker",
            "tool_call_id": "call-1",
            "model": {"name": "provider-model", "credential": "private-token"},
            "messages": [{"role": "user", "content": "private request"}],
            "tools": [{"name": "private tool schema"}],
            "model_settings": {"private": "provider payload"},
        }
    )
    capture.model_response(
        ModelResponse(
            timestamp="2026-07-31T00:00:00.000Z",
            namespace="root",
            agent_name="Primary",
            node="model",
            run_id="run-1",
            message_id="message-1",
            is_primary=True,
            usage={"input_tokens": 2, "output_token_details": {"reasoning": 1}},
            response_metadata={
                "finish_reason": "stop",
                "authorization": "Bearer private-token",
                "system_fingerprint": "fp-1",
            },
            additional_kwargs={"reasoning_content": "kept thought"},
            content_blocks=[{"type": "reasoning", "reasoning": "private thought"}],
            provider_finish_reason="stop",
            finish_reason_source="response_metadata.finish_reason",
        )
    )
    capture.output_event(
        OutputEvent(
            event_type="tool_result",
            phase="end",
            sequence=1,
            timestamp="2026-07-31T00:00:01.000Z",
            agent_name="Worker",
            node="tools",
            message="private tool result",
            values={
                "tool_name": "read_file",
                "tool_call_id": "call-1",
                "status": "completed",
                "output": "private file contents",
            },
        )
    )

    request, response, tool_result = capture.snapshot()
    assert request["data"] == {
        "agent_type": "context_worker",
        "agent_name": "Worker",
        "tool_call_id": "call-1",
        "model_name": "provider-model",
        "message_count": 1,
        "tool_count": 1,
    }
    assert response["timestamp"] == "2026-07-31T00:00:00.000Z"
    assert response["kind"] == "model_response"
    assert response["data"] == {
        "namespace": "root",
        "agent_name": "Primary",
        "node": "model",
        "run_id": "run-1",
        "message_id": "message-1",
        "is_primary": True,
        "provider_finish_reason": "stop",
        "finish_reason_source": "response_metadata.finish_reason",
        "finish_reason_category": "stop",
        "usage": {
            "input_tokens": 2,
            "output_token_details": {"reasoning": 1},
        },
        "stream_diagnostics": {},
    }
    assert tool_result["data"] == {
        "phase": "end",
        "namespace": "root",
        "agent_name": "Worker",
        "node": "tools",
        "tool_name": "read_file",
        "tool_call_id": "call-1",
        "status": "completed",
    }
    persisted = repr(capture.snapshot())
    for sensitive in (
        "private request",
        "private-token",
        "provider payload",
        "kept thought",
        "private thought",
        "private tool result",
        "private file contents",
    ):
        assert sensitive not in persisted


@pytest.mark.parametrize(
    ("reason", "category"),
    [
        ("stop", "stop"),
        ("length", "length"),
        ("content_filter", "content_filter"),
        ("tool_calls", "tool_calls"),
        ("vendor-specific", "unknown"),
        (None, "unknown"),
    ],
)
def test_finish_reason_categories_keep_unknown_provider_values_explicit(
    reason: str | None, category: str
) -> None:
    assert finish_reason_category(reason) == category

def test_agent_execution_closes_v3_stream_when_consumer_is_cancelled() -> None:
    async def scenario() -> bool:
        class BlockingRun:
            def __init__(self) -> None:
                self.pulling = asyncio.Event()
                self.exited = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
                self.exited = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                self.pulling.set()
                await asyncio.Event().wait()
                raise StopAsyncIteration

            async def output(self):
                return None

        class Graph:
            def __init__(self, run: BlockingRun) -> None:
                self.run = run

            async def astream_events(self, _input, *, config: dict, version: str):
                assert version == "v3"
                assert config == {"recursion_limit": 100}
                return self.run

        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"]["enabled"] = False
        settings["event_templates"]["lifecycle"] = {
            "enabled": True,
            "template": "{{message}}",
        }
        run = BlockingRun()
        execution = AgentExecution(
            graph=Graph(run),
            input_state={"messages": [{"role": "user", "content": "cancel me"}]},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
        )
        stream = execution.stream_text()
        assert await anext(stream) == "running"
        pending = asyncio.create_task(anext(stream))
        await asyncio.wait_for(run.pulling.wait(), timeout=1)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        return run.exited

    assert asyncio.run(scenario()) is True

def test_agent_execution_times_out_and_closes_v3_stream(monkeypatch) -> None:
    async def scenario() -> bool:
        class BlockingRun:
            def __init__(self) -> None:
                self.exited = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
                self.exited = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                await asyncio.Event().wait()
                raise StopAsyncIteration

            async def output(self):
                return None

        class Graph:
            def __init__(self, run: BlockingRun) -> None:
                self.run = run

            async def astream_events(self, _input, *, config: dict, version: str):
                assert config == {"recursion_limit": 100}
                assert version == "v3"
                return self.run

        monkeypatch.setattr(
            "agent_shell.runtime.agent_runtime.EXECUTION_TIMEOUT_SECONDS", 0.01
        )
        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"]["enabled"] = False
        settings["event_templates"]["lifecycle"] = {
            "enabled": True,
            "template": "{{message}}",
        }
        run = BlockingRun()
        execution = AgentExecution(
            graph=Graph(run),
            input_state={"messages": [{"role": "user", "content": "wait"}]},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
        )
        stream = execution.stream_text()
        assert await anext(stream) == "running"
        assert await anext(stream) == "failed"
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(stream)
        assert captured.value.code == "execution_timeout"
        return run.exited

    assert asyncio.run(scenario()) is True

def test_graph_recursion_failure_uses_step_limit_error() -> None:
    async def scenario() -> str:
        from langgraph.errors import GraphRecursionError

        class Graph:
            async def astream_events(self, _input, *, config: dict, version: str):
                raise GraphRecursionError("private graph state")

        execution = AgentExecution(
            graph=Graph(),
            input_state={"messages": [{"role": "user", "content": "loop"}]},
            rectifier=OutputEventRectifier(
                OutputProjector(config(mode="blocklist"))
            ),
            normalizer=V3EventNormalizer("Primary"),
        )
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(execution.stream_text())
        assert "private graph state" not in captured.value.safe_message
        return captured.value.code

    assert asyncio.run(scenario()) == "execution_step_limit"

def test_runtime_boundaries_classify_provider_and_tool_failures() -> None:
    def fail(_request):
        raise RuntimeError("private failure details")

    with pytest.raises(AgentRuntimeError) as tool_error:
        ToolErrorBoundaryMiddleware().wrap_tool_call(None, fail)
    with pytest.raises(AgentRuntimeError) as provider_error:
        ProviderErrorBoundaryMiddleware().wrap_model_call(None, fail)

    assert tool_error.value.code == "tool_execution_failed"
    assert provider_error.value.code == "provider_request_failed"
    assert "private failure details" not in tool_error.value.safe_message
    assert "private failure details" not in provider_error.value.safe_message

def test_tool_error_boundary_preserves_successful_result() -> None:
    result = ToolMessage(
        content="x" * 1_000_100,
        tool_call_id="call-large",
        name="large",
    )

    returned = ToolErrorBoundaryMiddleware().wrap_tool_call(None, lambda _request: result)

    assert returned is result
    assert returned.content == result.content

def test_unclassified_graph_failure_is_not_mislabeled_as_provider() -> None:
    async def scenario() -> str:
        class Graph:
            async def astream_events(self, _input, *, config: dict, version: str):
                raise RuntimeError("private middleware or graph details")

        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"]["enabled"] = False
        settings["event_templates"]["lifecycle"] = {
            "enabled": True,
            "template": "{{message}}",
        }
        execution = AgentExecution(
            graph=Graph(),
            input_state={"messages": [{"role": "user", "content": "fail"}]},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
        )
        stream = execution.stream_text()
        assert await anext(stream) == "running"
        assert await anext(stream) == "failed"
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(stream)
        assert "private middleware or graph details" not in captured.value.safe_message
        return captured.value.code

    assert asyncio.run(scenario()) == "agent_execution_failed"

def test_classified_graph_failure_emits_matching_lifecycle_error() -> None:
    async def scenario() -> str:
        class Graph:
            async def astream_events(self, _input, *, config: dict, version: str):
                raise AgentRuntimeError(
                    "provider_request_failed",
                    "The provider request failed.",
                    status_code=502,
                )

        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"]["enabled"] = False
        settings["event_templates"]["lifecycle"] = {
            "enabled": True,
            "template": "{{phase}}:{{error_code}}",
        }
        execution = AgentExecution(
            graph=Graph(),
            input_state={"messages": [{"role": "user", "content": "fail"}]},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
        )
        stream = execution.stream_text()
        assert await anext(stream) == "start:"
        assert await anext(stream) == "error:provider_request_failed"
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(stream)
        return captured.value.code

    assert asyncio.run(scenario()) == "provider_request_failed"
