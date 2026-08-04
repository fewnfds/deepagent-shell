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

def test_session_capture_persists_only_explicit_workflow_fields() -> None:
    capture = AgentRunCapture()
    capture.model_request(
        {
            "agent_type": "subagent",
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
        "agent_type": "subagent",
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
            automation=noop_automation(),
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
            automation=noop_automation(),
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
            automation=noop_automation(),
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
            automation=noop_automation(),
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
            automation=noop_automation(),
        )
        stream = execution.stream_text()
        assert await anext(stream) == "start:"
        assert await anext(stream) == "error:provider_request_failed"
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(stream)
        return captured.value.code

    assert asyncio.run(scenario()) == "provider_request_failed"
