from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from typing_extensions import NotRequired

from agent_shell.plugins.workflow_input_context.contracts import (
    DEFAULT_CUSTOM_TRANSFORM_SOURCE,
    WorkflowInputContextBlock,
)
from agent_shell.plugins.workflow_input_context.middleware import (
    WorkflowInputContextError,
    WorkflowInputContextMiddleware,
)
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import AgentShellState


class ToolCapableFakeModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class _WICOrderProbeMiddleware(AgentMiddleware[AgentShellState]):
    """Expose the WIC-before-custom ordering as observable middleware behavior."""

    state_schema = AgentShellState

    def before_agent(self, state, runtime):
        return {
            "shared_vars": {
                "custom_middleware_saw_wic": state.get("shared_vars", {}).get(
                    "wic_marker"
                )
            }
        }


def run_agent(
    block: WorkflowInputContextBlock,
    context_messages: tuple[dict[str, object], ...],
    *,
    files: dict[str, object] | None = None,
    workflow_state: dict[str, object] | None = None,
    additional_middleware: list[AgentMiddleware] | None = None,
    agent_scope: str = "main_agent",
    input_messages: list[object] | None = None,
):
    backend = StateBackend()
    agent = create_deep_agent(
        model=ToolCapableFakeModel(responses=["answer"]),
        backend=backend,
        state_schema=AgentShellState,
        middleware=[
            WorkflowInputContextMiddleware(
                block,
                backend=backend,
                agent_scope=agent_scope,
            ),
            *(additional_middleware or []),
        ],
    )
    input_state: dict[str, object] = {"messages": input_messages or []}
    if files is not None:
        input_state["files"] = files
    return agent.invoke(
        input_state,
        context=WorkflowRuntimeContext.from_request(
            context_messages,
            request_id="test-request",
            workflow={"id": "workflow-id"},
        ).for_workflow_agent(
            workflow_state or {},
            workflow_node_id="agent-current",
            agent_id="agent-id",
            invocation_id="invocation-current",
        ),
    )


def message_signature(result: dict[str, object]) -> list[tuple[str, str]]:
    return [
        (str(message.type), str(message.content))
        for message in result["messages"]
    ]


def test_before_agent_injects_snapshot_and_applies_system_policy() -> None:
    source_messages = (
        {"role": "system", "content": "base"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "system", "content": "long system instruction"},
        {"role": "system", "content": "x"},
        {"role": "user", "content": "question"},
    )
    result = run_agent(
        WorkflowInputContextBlock(
            name="input",
            system_promote_min_chars=10,
        ),
        source_messages,
    )

    assert message_signature(result) == [
        ("system", "base"),
        ("system", "long system instruction"),
        ("ai", "answer 1"),
        ("human", "x"),
        ("human", "question"),
        ("ai", "answer"),
    ]


def test_default_transform_template_is_inert_until_enabled() -> None:
    block = WorkflowInputContextBlock(name="input")

    assert block.custom_transform_source == DEFAULT_CUSTOM_TRANSFORM_SOURCE
    assert block.custom_transform_enabled is False


def test_workflow_input_context_runs_before_custom_before_agent_middleware() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    return {'shared_vars': {'wic_marker': 'ready'}}\n"
        ),
    )

    result = run_agent(
        block,
        ({"role": "user", "content": "question"},),
        additional_middleware=[_WICOrderProbeMiddleware()],
    )

    assert result["shared_vars"]["custom_middleware_saw_wic"] == "ready"


def test_subagent_uses_delegated_messages_without_root_request_or_duplicates() -> None:
    result = run_agent(
        WorkflowInputContextBlock(name="input"),
        ({"role": "user", "content": "original workflow request"},),
        agent_scope="subagent",
        input_messages=[HumanMessage(content="delegated task")],
    )

    assert message_signature(result) == [
        ("human", "delegated task"),
        ("ai", "answer"),
    ]


def test_subagent_preserves_delegated_tool_call_pair() -> None:
    result = run_agent(
        WorkflowInputContextBlock(name="input"),
        ({"role": "user", "content": "original workflow request"},),
        agent_scope="subagent",
        input_messages=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup",
                        "args": {"query": "delegated"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="tool result", tool_call_id="call-1"),
            HumanMessage(content="continue"),
        ],
    )

    messages = result["messages"]
    assert messages[0].tool_calls[0]["id"] == "call-1"
    assert messages[1].tool_call_id == "call-1"
    assert message_signature(result) == [
        ("ai", ""),
        ("tool", "tool result"),
        ("human", "continue"),
        ("ai", "answer"),
    ]


def test_async_hook_uses_backend_aread_for_slots() -> None:
    class AsyncReadBackend:
        def read(self, *_args, **_kwargs):
            raise AssertionError("async hook must not use sync backend read")

        async def aread(self, path, *, offset, limit):
            assert (path, offset, limit) == ("/slot.txt", 0, 1_000_000)
            return SimpleNamespace(file_data=create_file_data("slot content"), error=None)

    middleware = WorkflowInputContextMiddleware(
        WorkflowInputContextBlock(
            name="input",
            system_promote_enabled=False,
            demote_non_top_system=False,
            slots=[{"role": "system", "file": "/slot.txt", "max_chars": 4}],
        ),
        backend=AsyncReadBackend(),
        agent_scope="main_agent",
    )
    context = WorkflowRuntimeContext.from_request(
        ({"role": "user", "content": "question"},),
        request_id="test-request",
        workflow={"id": "workflow-id"},
    )

    update = asyncio.run(
        middleware.abefore_agent({"messages": []}, SimpleNamespace(context=context))
    )

    assert update is not None
    assert [message.content for message in update["messages"].value] == [
        "question",
        "slot",
    ]


def test_custom_transform_reads_shared_filesystem_without_mutating_context() -> None:
    source_messages = ({"role": "user", "content": "question"},)
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        demote_non_top_system=False,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    messages = [dict(message) for message in context.messages]\n"
            "    messages.append({'role': 'system', 'content': read_file('/extra.txt')})\n"
            "    return {'messages': messages}\n"
        ),
    )
    result = run_agent(
        block,
        source_messages,
        files={"/extra.txt": create_file_data("from file")},
    )

    assert message_signature(result) == [
        ("human", "question"),
        ("system", "from file"),
        ("ai", "answer"),
    ]
    assert source_messages == ({"role": "user", "content": "question"},)


def test_slot_fallback_and_missing_truncation_stop_later_slots() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        system_promote_enabled=False,
        demote_non_top_system=False,
        slots=[
            {
                "role": "user",
                "file": "/missing.txt",
                "fallback_files": ["/fallback.txt"],
                "literal": "unused",
                "max_chars": 4,
            },
            {
                "role": "assistant",
                "file": "/also-missing.txt",
                "truncate_if_missing": True,
            },
            {"role": "system", "literal": "must-not-appear"},
        ],
    )
    result = run_agent(
        block,
        ({"role": "user", "content": "question"},),
        files={"/fallback.txt": create_file_data("fallback text")},
    )

    assert message_signature(result) == [
        ("human", "question"),
        ("human", "fall"),
        ("ai", "answer"),
    ]


def test_custom_transform_rejects_invalid_return_without_exposing_details() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    return 'must-not-leak'\n"
        ),
    )

    with pytest.raises(WorkflowInputContextError, match="invalid state update") as exc_info:
        run_agent(block, ({"role": "user", "content": "question"},))

    assert "must-not-leak" not in str(exc_info.value)


def test_custom_transform_reader_rejects_host_paths() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    read_file('C:\\\\private.txt')\n"
            "    return {'messages': list(context.messages)}\n"
        ),
    )

    with pytest.raises(WorkflowInputContextError, match="workflow filesystem path is invalid"):
        run_agent(block, ({"role": "user", "content": "question"},))


def test_custom_transform_selects_prior_invocation_from_parent_workflow_state() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        demote_non_top_system=False,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    prior = next(record for record in workflow_state['agent_invocations'].values() "
            "if record['workflow_node_id'] == 'agent-prior')\n"
            "    final = prior['messages'][-1]\n"
            "    return {'messages': [{'role': 'user', 'content': final.content}]}\n"
        ),
    )
    prior = AIMessage(content="selected prior result", id="final-prior")

    result = run_agent(
        block,
        ({"role": "user", "content": "original request"},),
        workflow_state={
            "agent_invocations": {
                "invocation-prior": {
                    "invocation_id": "invocation-prior",
                    "workflow_id": "workflow-id",
                    "workflow_node_id": "agent-prior",
                    "agent_id": "prior-agent-id",
                    "invoked_at": 1.0,
                    "messages": [prior],
                }
            }
        },
    )

    assert message_signature(result) == [
        ("human", "selected prior result"),
        ("ai", "answer"),
    ]


class _ExtendedState(AgentState):
    selected_invocation: NotRequired[str]


class _StateExtensionMiddleware(AgentMiddleware[_ExtendedState]):
    state_schema = _ExtendedState


def test_transform_channels_are_validated_by_the_merged_agent_state_schema() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        custom_transform_source=(
            "def transform(read_file, config, workflow_state, agent_state, context):\n"
            "    return {\n"
            "        'messages': list(context.messages),\n"
            "        'selected_invocation': context.invocation_id,\n"
            "    }\n"
        ),
    )

    result = run_agent(
        block,
        ({"role": "user", "content": "question"},),
        additional_middleware=[_StateExtensionMiddleware()],
    )

    assert result["selected_invocation"] == "invocation-current"
