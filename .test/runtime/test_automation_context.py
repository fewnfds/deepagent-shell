from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.runtime.input_messages import validate_client_messages

from .automation_support import write_plugin


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
    recursive = runtime.child_context(
        "child-id", child, "call-recursive"
    )["agent_shell_invocation"]

    assert root["parent_id"] == root["cause_tool_call_id"] == ""
    assert child["parent_id"] == root["id"]
    assert child["cause_tool_call_id"] == "call-child"
    assert recursive["parent_id"] == child["id"]
    assert recursive["cause_tool_call_id"] == "call-recursive"
    assert len({root["id"], child["id"], recursive["id"]}) == 3
    workspaces = [
        item["workspaces"]["hook:0"] for item in (root, child, recursive)
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
async def test_multimodal_request_is_recursively_frozen_and_owner_copies_are_isolated(
    tmp_path: Path,
) -> None:
    write_plugin(
        tmp_path / "plugins",
        "copy-request-plugin",
        "async def prepare(ctx):\n    ctx.messages.extend(ctx.request.messages)\n",
        entrypoints=("prepare",),
    )
    binding = {
        "plugin_id": "copy-request-plugin",
        "enabled": True,
        "config": {},
    }
    owners = [
        AutomationOwner(
            id=owner_id,
            type=owner_type,
            name=owner_id,
            automation={"hooks": [binding], "periodic": []},
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
    main_agent = runtime.messages_for("main_agent")
    child = runtime.messages_for("child")
    main_agent[0]["content"][1]["url"] = "https://changed.example/image.png"
    assert child[0]["content"][1]["url"] == "https://media.example/image.png"
    assert runtime.messages_for("main_agent")[0]["content"][1]["url"] == (
        "https://media.example/image.png"
    )
    await runtime.finish({"status": "completed"})
