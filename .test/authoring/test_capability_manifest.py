from __future__ import annotations

import subprocess
import sys

import pytest

from agent_shell.authoring import (
    DELETE_TOOL_DESCRIPTION,
    EDIT_FILE_TOOL_DESCRIPTION,
    EXECUTE_TOOL_DESCRIPTION,
    FILESYSTEM_EDITOR_SYSTEM_PROMPT,
    GLOB_TOOL_DESCRIPTION,
    GREP_TOOL_DESCRIPTION,
    LIST_FILES_TOOL_DESCRIPTION,
    READ_FILE_TOOL_DESCRIPTION,
    SKILLS_SYSTEM_PROMPT,
    SUBAGENT_EDITOR_SYSTEM_PROMPT,
    TASK_TOOL_DESCRIPTION,
    WRITE_FILE_TOOL_DESCRIPTION,
    WRITE_TODOS_SYSTEM_PROMPT,
    WRITE_TODOS_TOOL_DESCRIPTION,
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
    PROMPT_PRESET_TEMPLATE_FIELDS,
)


def test_manifest_matches_current_blocks_and_form_order() -> None:
    assert [manifest.type for manifest in CAPABILITY_MANIFESTS] == [
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
    ]
    assert {manifest.type for manifest in CAPABILITY_MANIFESTS} == set(BLOCK_MODELS)
    assert CAPABILITY_MANIFESTS[0].required is True
    manifests = {manifest.type: manifest for manifest in CAPABILITY_MANIFESTS}
    assert manifests["custom-middleware"].subagent_overrideable is True
    assert manifests["filesystem"].subagent_overrideable is False
    assert manifests["filesystem"].subagent_policy == "inherit"
    assert manifests["filesystem"].required is False
    assert manifests["output-mode"].subagent_overrideable is False
    assert manifests["output-mode"].required is True
    assert manifests["output-mode"].subagent_policy == "top-level-only"
    assert manifests["output-mode"].tool_names == ()
    assert manifests["exception-retry"].subagent_overrideable is True
    assert manifests["exception-retry"].subagent_policy == "inherit"
    assert manifests["exception-retry"].tool_names == ()
    assert manifests["subagent"].subagent_overrideable is False
    assert manifests["todo-list"].subagent_overrideable is True
    assert manifests["todo-list"].tool_names == ("write_todos",)
    assert manifests["prompt-preset"].subagent_overrideable is True
    assert manifests["prompt-preset"].subagent_policy == "inherit"


def test_manifest_rejects_invalid_catalog_structure() -> None:
    with pytest.raises(ValueError, match="types must be unique"):
        validate_capability_manifests((*CAPABILITY_MANIFESTS, CAPABILITY_MANIFESTS[0]))

    with pytest.raises(ValueError, match="orders must be unique and ordered"):
        validate_capability_manifests(tuple(reversed(CAPABILITY_MANIFESTS)))



def test_editor_defaults_are_derived_from_current_authoring_contracts() -> None:
    defaults = editor_defaults()
    filesystem = defaults["filesystem"]
    output = defaults["output_mode"]
    prompt_preset = defaults["prompt_preset"]

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
    assert defaults["subagent"]["system_prompt"] == ""
    assert set(defaults["subagent"]) == {"system_prompt", "tool_description"}
    assert set(defaults["todo_list"]) == {"system_prompt", "tool_description"}
    assert filesystem["tool_token_limit_before_evict"] == (
        FilesystemBlock.model_fields["tool_token_limit_before_evict"].default
    )
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
    assert prompt_preset == {
        "template_variables": [f"{{{field}}}" for field in PROMPT_PRESET_TEMPLATE_FIELDS],
    }


def test_editor_text_snapshots_match_locked_upstream_defaults() -> None:
    from deepagents.middleware import filesystem, skills, subagents
    from langchain.agents.middleware import todo

    assert FILESYSTEM_EDITOR_SYSTEM_PROMPT == ""
    assert not hasattr(filesystem, "FILESYSTEM_SYSTEM_PROMPT")
    assert LIST_FILES_TOOL_DESCRIPTION == filesystem.LIST_FILES_TOOL_DESCRIPTION
    assert READ_FILE_TOOL_DESCRIPTION == filesystem.READ_FILE_TOOL_DESCRIPTION
    assert WRITE_FILE_TOOL_DESCRIPTION == filesystem.WRITE_FILE_TOOL_DESCRIPTION
    assert EDIT_FILE_TOOL_DESCRIPTION == filesystem.EDIT_FILE_TOOL_DESCRIPTION
    assert DELETE_TOOL_DESCRIPTION == filesystem.DELETE_TOOL_DESCRIPTION
    assert GLOB_TOOL_DESCRIPTION == filesystem.GLOB_TOOL_DESCRIPTION
    assert GREP_TOOL_DESCRIPTION == filesystem.GREP_TOOL_DESCRIPTION
    assert EXECUTE_TOOL_DESCRIPTION.startswith(
        filesystem.EXECUTE_TOOL_DESCRIPTION.rstrip()
    )
    assert "bundled runtime" in EXECUTE_TOOL_DESCRIPTION
    assert "do not assume they are installed" in EXECUTE_TOOL_DESCRIPTION
    assert SKILLS_SYSTEM_PROMPT == skills.SKILLS_SYSTEM_PROMPT
    assert SUBAGENT_EDITOR_SYSTEM_PROMPT == ""
    assert TASK_TOOL_DESCRIPTION == subagents.TASK_TOOL_DESCRIPTION
    assert WRITE_TODOS_SYSTEM_PROMPT == todo.WRITE_TODOS_SYSTEM_PROMPT
    assert WRITE_TODOS_TOOL_DESCRIPTION == todo.WRITE_TODOS_TOOL_DESCRIPTION

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
