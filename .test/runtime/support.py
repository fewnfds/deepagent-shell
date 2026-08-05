from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agent_shell.runtime.agent_builder import _build_chat_model
from agent_shell.runtime.agent_runtime import AgentExecution
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import OutputProjector
from agent_shell.runtime.limits import (
    ProviderErrorBoundaryMiddleware,
    ToolErrorBoundaryMiddleware,
)
from agent_shell.runtime.output_stream import (
    ModelCallBoundary,
    OutputEvent,
    V3EventNormalizer,
)


EVENT_TYPES = (
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "tool_error",
    "subagent",
    "custom",
    "lifecycle",
)


@pytest.fixture
def provider_http_clients():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    sync_client = httpx.Client(transport=httpx.MockTransport(handler))
    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    clients = SimpleNamespace(
        sync_client=sync_client,
        async_client=async_client,
    )
    try:
        yield clients
    finally:
        sync_client.close()
        asyncio.run(async_client.aclose())


def config(
    *,
    mode: str,
    mappings: list[dict[str, str]] | None = None,
    template: str = "{{message}}",
) -> dict:
    return {
        "filter_mode": mode,
        "filter_mappings": mappings or [],
        "variable_encoding": "html",
        "event_templates": {
            event_type: {
                "enabled": event_type == "assistant_text",
                "template": template,
            }
            for event_type in EVENT_TYPES
        },
    }


def message_envelope(
    payload: dict,
    *,
    run_id: str = "run-primary",
    agent_name: str = "Primary",
    namespace: list[str] | None = None,
    timestamp: int = 1,
) -> dict:
    return {
        "method": "messages",
        "params": {
            "namespace": namespace or [],
            "timestamp": timestamp,
            "data": (
                payload,
                {
                    "run_id": run_id,
                    "lc_agent_name": agent_name,
                    "langgraph_node": "model",
                },
            ),
        },
    }


class EventRun:
    def __init__(self, events: list[dict]) -> None:
        self._events = iter(events)

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def __aiter__(self):
        async def events():
            for event in self._events:
                yield event

        return events()

    async def output(self):
        return None


class EventGraph:
    def __init__(self, events: list[dict]) -> None:
        self._events = events

    async def astream_events(self, _input, *, config: dict, version: str):
        assert config == {"recursion_limit": 100}
        assert version == "v3"
        return EventRun(self._events)


class NoopAutomation:
    @property
    def graph_stop_requested(self) -> bool:
        return False

    async def wait_for_graph_stop(self) -> None:
        await asyncio.Event().wait()

    @staticmethod
    def graph_stop_error() -> AgentRuntimeError:
        raise AssertionError("Noop automation cannot request a graph stop")

    async def start(self) -> None:
        pass

    async def finish(self, _terminal) -> None:
        pass


def noop_automation() -> NoopAutomation:
    return NoopAutomation()


class NoopMediaResponse:
    @staticmethod
    async def project(_event) -> None:
        return None

    @property
    def assets(self) -> list[dict]:
        return []

    @staticmethod
    def structured_blocks(_response) -> list[dict]:
        return []


def noop_media_response() -> NoopMediaResponse:
    return NoopMediaResponse()
