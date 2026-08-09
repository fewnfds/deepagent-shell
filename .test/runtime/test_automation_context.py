from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.runtime.input_messages import validate_client_messages
from agent_shell.validation.service import StaticAssembly

from .automation_support import write_plugin


def _assembly(plugin_id: str, plugin_config: dict[str, object]) -> StaticAssembly:
    return StaticAssembly(
        main_agent={
            "id": "main_agent-id",
            "component_name": "Main component",
            "name": "Main Agent",
        },
        references={},
        blocks={},
        filesystem_mode="default-shared",
        automation={
            "hooks": [{
                "plugin_id": plugin_id,
                "enabled": True,
                "config": plugin_config,
            }],
            "periodic": [],
        },
        subagents=(),
        subagent_nodes={},
    )


def test_lifecycle_snapshot_freezes_input_and_hashes_plugin_references_only(
    tmp_path: Path,
) -> None:
    messages = validate_client_messages(
        [{"role": "user", "content": "hello"}]
    )

    def build(plugin_id: str, plugin_config: dict[str, object]) -> AutomationRuntime:
        return AutomationRuntime.from_assembly(
            _assembly(plugin_id, plugin_config),
            messages,
            main_agent_id="main_agent-id",
            request_id="request-id",
            plugins_dir=tmp_path / "plugins",
            skills_dir=tmp_path / "skills",
            runtime_root=tmp_path / "runtime",
        )

    first = build("prompt-plugin", {"seed": 1})
    changed_config = build("prompt-plugin", {"seed": 2})
    changed_reference = build("other-plugin", {"seed": 1})

    assert first.lifecycle.messages == first.request.messages
    assert len(first.lifecycle.input_sha) == 64
    assert len(first.lifecycle.assembly_sha) == 64
    assert set(first.lifecycle.agent_shas) == {"main_agent-id"}
    assert len(first.lifecycle.agent_shas["main_agent-id"]) == 64
    assert first.lifecycle.assembly_sha == changed_config.lifecycle.assembly_sha
    assert first.lifecycle.assembly_sha != changed_reference.lifecycle.assembly_sha
    assert "config" not in first.lifecycle.assembly["main_agent"]["automation"][
        "hooks"
    ][0]
    with pytest.raises(TypeError):
        first.lifecycle.assembly["main_agent"]["name"] = "changed"


def test_invocation_context_is_read_only_and_preserves_nested_parent_chain(
    tmp_path: Path,
) -> None:
    binding = {
        "plugin_id": "workspace-plugin",
        "enabled": True,
        "config": {},
    }
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=[
            AutomationOwner(
                id="main_agent-id",
                type="main_agent",
                name="Main Agent",
                automation={"hooks": [binding], "periodic": []},
                mapped_paths={},
            ),
            AutomationOwner(
                id="child-id",
                type="subagent",
                name="Worker",
                automation={"hooks": [binding], "periodic": []},
                mapped_paths={},
            ),
        ],
        client_messages=[],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    root = runtime.root_context("main_agent-id")["agent_shell_invocation"]
    child = runtime.child_context(
        "child-id", root, "call-child"
    )["agent_shell_invocation"]
    second_child = runtime.child_context(
        "child-id", root, "call-second-child"
    )["agent_shell_invocation"]

    assert root["parent_id"] == root["cause_tool_call_id"] == ""
    assert child["parent_id"] == root["id"]
    assert child["cause_tool_call_id"] == "call-child"
    assert second_child["parent_id"] == root["id"]
    assert second_child["cause_tool_call_id"] == "call-second-child"
    assert len({root["id"], child["id"], second_child["id"]}) == 3
    workspaces = [
        item["workspaces"]["hook:0"] for item in (root, child, second_child)
    ]
    assert len(set(workspaces)) == 3
    assert all(path.is_dir() for path in workspaces)
    with pytest.raises(TypeError):
        child["id"] = "changed"
    with pytest.raises(TypeError):
        child["workspaces"]["hook:0"] = tmp_path

    asyncio.run(runtime.finish({"status": "completed"}))
    assert not (tmp_path / "runtime" / "automation" / "request-id").exists()


@pytest.mark.anyio
async def test_multimodal_request_is_recursively_frozen_for_the_lifecycle(
    tmp_path: Path,
) -> None:
    owners = [
        AutomationOwner(
            id=owner_id,
            type=owner_type,
            name=owner_id,
            automation={"hooks": [], "periodic": []},
            mapped_paths={},
        )
        for owner_id, owner_type in (("main_agent", "main_agent"), ("child", "subagent"))
    ]
    messages = validate_client_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect"},
                    {"type": "image", "url": "https://media.example/image.png"},
                ],
            }
        ]
    )
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=owners,
        client_messages=messages,
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    await runtime.prepare()

    with pytest.raises(TypeError):
        runtime.request.messages[0]["content"][1]["url"] = "changed"
    with pytest.raises(AttributeError):
        runtime.request.messages[0]["content"].append({"type": "text", "text": "x"})
    assert runtime.lifecycle.messages is runtime.request.messages
    assert runtime.lifecycle.messages[0]["content"][1]["url"] == (
        "https://media.example/image.png"
    )
    await runtime.finish({"status": "completed"})
