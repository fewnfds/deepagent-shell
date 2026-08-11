from __future__ import annotations

import pytest
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agent_shell.plugins.workflow_input_context.contracts import (
    DEFAULT_CUSTOM_TRANSFORM_SOURCE,
    WorkflowInputContextBlock,
)
from agent_shell.plugins.workflow_input_context.middleware import (
    WorkflowInputContextError,
    WorkflowInputContextMiddleware,
)
from agent_shell.runtime.context import WorkflowRuntimeContext


class ToolCapableFakeModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def run_agent(
    block: WorkflowInputContextBlock,
    context_messages: tuple[dict[str, object], ...],
    *,
    files: dict[str, object] | None = None,
    scope: str = "main_agent",
):
    backend = StateBackend()
    agent = create_deep_agent(
        model=ToolCapableFakeModel(responses=["answer"]),
        backend=backend,
        middleware=[
            WorkflowInputContextMiddleware(
                block,
                backend=backend,
                scope=scope,
            )
        ],
    )
    input_state: dict[str, object] = {"messages": []}
    if files is not None:
        input_state["files"] = files
    return agent.invoke(
        input_state,
        context=WorkflowRuntimeContext.from_request(
            context_messages,
            request_id="test-request",
            workflow={},
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


def test_scope_can_skip_main_and_apply_to_subagent() -> None:
    block = WorkflowInputContextBlock(name="input", apply_to=["subagent"])
    source_messages = ({"role": "user", "content": "question"},)

    main_result = run_agent(block, source_messages, scope="main_agent")
    subagent_result = run_agent(block, source_messages, scope="subagent")

    assert message_signature(main_result) == [("ai", "answer")]
    assert message_signature(subagent_result) == [
        ("human", "question"),
        ("ai", "answer"),
    ]


def test_custom_transform_reads_shared_filesystem_without_mutating_context() -> None:
    source_messages = ({"role": "user", "content": "question"},)
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        demote_non_top_system=False,
        custom_transform_source=(
            "def transform(messages, read_file, config):\n"
            "    messages.append({'role': 'system', 'content': read_file('/extra.txt')})\n"
            "    return messages\n"
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
            "def transform(messages, read_file, config):\n"
            "    return {'secret': 'must-not-leak'}\n"
        ),
    )

    with pytest.raises(WorkflowInputContextError, match="input context messages are invalid") as exc_info:
        run_agent(block, ({"role": "user", "content": "question"},))

    assert "must-not-leak" not in str(exc_info.value)


def test_custom_transform_reader_rejects_host_paths() -> None:
    block = WorkflowInputContextBlock(
        name="input",
        custom_transform_enabled=True,
        custom_transform_source=(
            "def transform(messages, read_file, config):\n"
            "    read_file('C:\\\\private.txt')\n"
            "    return messages\n"
        ),
    )

    with pytest.raises(WorkflowInputContextError, match="workflow filesystem path is invalid"):
        run_agent(block, ({"role": "user", "content": "question"},))
