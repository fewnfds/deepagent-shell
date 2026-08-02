from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_shell.contracts import validate_block_payload
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.prompt_preset import prepare_agent_input


def preset(**updates) -> dict:
    value = {
        "name": "Agent startup",
        "tag_replacements": [
            {"tag": "|||requirements|||", "replacement": "fixed guidance"}
        ],
        "startup_messages": [
            {"role": "user", "content_template": "Task: {task}"},
            {"role": "assistant", "content_template": "Understood."},
            {"role": "user", "content_template": "Begin now."},
        ],
    }
    value.update(updates)
    return validate_block_payload("prompt-preset", value)


def test_prompt_preset_contract_is_literal_and_requires_content() -> None:
    validated = preset()
    assert validated["tag_replacements"][0]["tag"] == "|||requirements|||"

    with pytest.raises(ValidationError):
        validate_block_payload(
            "prompt-preset",
            {"name": "Empty", "tag_replacements": [], "startup_messages": []},
        )
    with pytest.raises(ValidationError):
        preset(
            tag_replacements=[
                {"tag": "|||one|||", "replacement": ""},
                {"tag": "|||one|||extra", "replacement": ""},
            ]
        )
    with pytest.raises(ValidationError):
        preset(tag_replacements=[{"tag": "line\nbreak", "replacement": ""}])
    with pytest.raises(ValidationError):
        preset(
            startup_messages=[
                {"role": "user", "content_template": "Begin as {agent_name}."}
            ]
        )


def test_prepare_agent_input_replaces_once_and_appends_ordered_messages() -> None:
    original = [
        {"role": "system", "content": "keep |||requirements|||"},
        {"role": "user", "content": "before |||requirements||| after"},
        {"role": "assistant", "content": "earlier response"},
    ]

    prepared = prepare_agent_input(
        original,
        preset(),
        variables={"task": "review {literal}"},
    )

    assert prepared.messages == [
        {"role": "system", "content": "keep |||requirements|||"},
        {"role": "user", "content": "before fixed guidance after"},
        {"role": "assistant", "content": "earlier response"},
        {"role": "user", "content": "Task: review {literal}"},
        {"role": "assistant", "content": "Understood."},
        {"role": "user", "content": "Begin now."},
    ]
    assert prepared.matched_tag_count == 1
    assert prepared.startup_message_count == 3
    assert original[1]["content"] == "before |||requirements||| after"


def test_replacement_output_is_not_rescanned_and_duplicate_match_fails() -> None:
    configured = preset(
        tag_replacements=[
            {"tag": "|||one|||", "replacement": "contains |||two|||"},
            {"tag": "|||two|||", "replacement": "second"},
        ]
    )
    prepared = prepare_agent_input(
        [{"role": "user", "content": "|||one|||"}],
        configured,
        variables={"task": "x"},
    )
    assert prepared.messages[0]["content"] == "contains |||two|||"

    with pytest.raises(AgentRuntimeError) as caught:
        prepare_agent_input(
            [
                {"role": "user", "content": "|||one|||"},
                {"role": "user", "content": "again |||one|||"},
            ],
            configured,
            variables={"task": "x"},
        )
    assert caught.value.code == "ambiguous_prompt_tag"


def test_missing_runtime_variable_returns_stable_prompt_error() -> None:
    with pytest.raises(AgentRuntimeError) as caught:
        prepare_agent_input([], preset(), variables={})

    assert caught.value.code == "prompt_preset_variable_unavailable"
    assert caught.value.status_code == 422
