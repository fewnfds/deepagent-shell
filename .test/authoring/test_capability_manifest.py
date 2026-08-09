from __future__ import annotations

import subprocess
import sys

import pytest

from agent_shell.authoring import (
    editor_defaults,
)
from agent_shell.capability_manifest import (
    CAPABILITY_BY_TYPE,
    CAPABILITY_MANIFESTS,
    validate_capability_manifests,
)
from agent_shell.contracts import (
    BLOCK_MODELS,
    FilesystemBlock,
    OUTPUT_COMMON_TEMPLATE_VARIABLES,
    OUTPUT_EVENT_NAMES,
    OUTPUT_EVENT_TEMPLATE_VARIABLES,
    OutputModeBlock,
)


def test_manifest_matches_current_blocks_and_form_order() -> None:
    assert [manifest.type for manifest in CAPABILITY_MANIFESTS] == [
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
        "other",
    ]
    assert {manifest.type for manifest in CAPABILITY_MANIFESTS} == set(BLOCK_MODELS)
    assert CAPABILITY_MANIFESTS[0].required is True
    manifests = {manifest.type: manifest for manifest in CAPABILITY_MANIFESTS}
    assert manifests["custom-middleware"].subagent_overrideable is True
    assert manifests["filesystem"].subagent_overrideable is False
    assert manifests["filesystem"].subagent_policy == "inherit"
    assert manifests["filesystem"].required is False
    assert manifests["filesystem-permissions"].subagent_overrideable is True
    assert manifests["filesystem-permissions"].subagent_policy == "inherit"
    assert manifests["filesystem-permissions"].required is False
    assert manifests["output-mode"].subagent_overrideable is False
    assert manifests["output-mode"].required is True
    assert manifests["output-mode"].subagent_policy == "top-level-only"
    assert manifests["output-mode"].tool_names == ()
    assert manifests["exception-retry"].subagent_overrideable is True
    assert manifests["exception-retry"].subagent_policy == "inherit"
    assert manifests["exception-retry"].tool_names == ()
    assert manifests["subagent"].subagent_overrideable is False
    assert manifests["subagent"].subagent_policy == "top-level-only"
    assert manifests["other"].subagent_overrideable is True
    assert manifests["other"].subagent_policy == "inherit"
    assert manifests["todo-list"].subagent_overrideable is True
    assert manifests["todo-list"].tool_names == ("write_todos",)


def test_manifest_rejects_invalid_catalog_structure() -> None:
    with pytest.raises(ValueError, match="types must be unique"):
        validate_capability_manifests((*CAPABILITY_MANIFESTS, CAPABILITY_MANIFESTS[0]))

    with pytest.raises(ValueError, match="orders must be unique and ordered"):
        validate_capability_manifests(tuple(reversed(CAPABILITY_MANIFESTS)))



def test_editor_defaults_are_derived_from_current_authoring_contracts() -> None:
    defaults = editor_defaults()
    filesystem = defaults["filesystem"]
    filesystem_permissions = defaults["filesystem_permissions"]
    output = defaults["output_mode"]

    assert [tool["name"] for tool in filesystem["tools"]] == list(
        CAPABILITY_BY_TYPE["filesystem"].tool_names
    )
    tools = {tool["name"]: tool for tool in filesystem["tools"]}
    assert tools["read_file"]["configurable"] is False
    assert tools["read_file"]["visible"] is True
    assert tools["delete"]["configurable"] is True
    assert tools["delete"]["visible"] is False
    assert tools["execute"]["configurable"] is False
    assert tools["execute"]["visible"] is False
    assert filesystem["system_prompt"] == ""
    assert filesystem_permissions["system_prompt"] == ""
    assert filesystem_permissions["tools"] == filesystem["tools"]
    assert defaults["subagent"]["system_prompt"] == ""
    assert set(defaults["subagent"]) == {"system_prompt", "tool_description"}
    assert set(defaults["todo_list"]) == {"system_prompt", "tool_description"}
    assert filesystem["tool_token_limit_before_evict"] == (
        FilesystemBlock.model_fields["tool_token_limit_before_evict"].default
    )
    assert filesystem["human_message_token_limit_before_evict"] == 50_000
    assert filesystem["grep_max_count"] == 1_000
    assert filesystem["max_execute_timeout"] == 3_600
    assert defaults["other"]["summarization"]["trigger"] == {
        "type": "auto",
        "value": None,
    }
    from deepagents.middleware.summarization import DEEPAGENTS_DEFAULT_SUMMARY_PROMPT

    assert defaults["other"]["summary_prompt_default"] == (
        DEEPAGENTS_DEFAULT_SUMMARY_PROMPT
    )
    assert defaults["other"]["prompt_caching"] == {
        "enabled": True,
        "type": "ephemeral",
        "ttl": "5m",
        "min_messages_to_cache": 0,
    }
    assert [event["key"] for event in output["events"]] == list(OUTPUT_EVENT_NAMES)
    assert output["events"][0]["variables"] == [
        *OUTPUT_COMMON_TEMPLATE_VARIABLES,
        *OUTPUT_EVENT_TEMPLATE_VARIABLES[OUTPUT_EVENT_NAMES[0]],
    ]
    assert all("streaming" not in event for event in output["events"])
    assert output["default_value"]["variable_encoding"] == "plain"
    assert all(
        setting["enabled"]
        for setting in output["default_value"]["event_templates"].values()
    )
    assert output["default_value"]["event_templates"]["assistant_text"] == {
        "enabled": True,
        "template": "{{message}}",
    }
    assert all(
        "<details><summary>" in setting["template"]
        and "{{message}}\n\n" in setting["template"]
        and "</details>" in setting["template"]
        for name, setting in output["default_value"]["event_templates"].items()
        if name != "assistant_text"
    )
    assert all(
        set(setting) == {"enabled", "template"}
        for setting in output["default_value"]["event_templates"].values()
    )
    OutputModeBlock.model_validate(
        {"name": "Output default", **output["default_value"]}
    )


def test_editor_catalog_import_does_not_load_optional_runtime_packages() -> None:
    program = """
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'deepagents' or name.startswith('deepagents.') or name == 'langchain' or name.startswith('langchain.'):
        raise AssertionError(f'optional runtime import during editor catalog construction: {name}')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from agent_shell.authoring import editor_defaults
assert editor_defaults()['filesystem']['tools']
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
