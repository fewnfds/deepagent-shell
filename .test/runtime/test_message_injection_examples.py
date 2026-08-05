from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, RemoveMessage

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.automation.scripts import scan_automation_scripts


_EXAMPLES = (
    Path(__file__).resolve().parents[2] / "examples" / "automation-plugins"
)


def _install_example(tmp_path: Path, plugin_id: str) -> str:
    source = _EXAMPLES / plugin_id
    destination = tmp_path / "plugins" / plugin_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    manifest = json.loads((destination / "script.json").read_text(encoding="utf-8"))
    return str(
        manifest["config_schema"]["properties"]["transform_source"]["default"]
    )


def _runtime(
    tmp_path: Path,
    *,
    owner_type: str,
    plugin_id: str,
    transform_source: str,
    messages: list[dict[str, object]],
) -> AutomationRuntime:
    owner_id = "primary" if owner_type == "primary" else "child"
    return AutomationRuntime(
        request_id=f"request-{owner_type}",
        owners=[
            AutomationOwner(
                id=owner_id,
                type=owner_type,
                name=owner_id.title(),
                automation={
                    "hooks": [{
                        "plugin_id": plugin_id,
                        "enabled": True,
                        "config": {"transform_source": transform_source},
                    }],
                    "periodic": [],
                },
                mapped_paths={},
            )
        ],
        client_messages=messages,
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )


def test_example_manifests_satisfy_the_current_plugin_contract(tmp_path: Path) -> None:
    for plugin_id in (
        "primary-message-injection",
        "subagent-message-injection",
    ):
        _install_example(tmp_path, plugin_id)

    result = scan_automation_scripts(tmp_path / "plugins")

    assert [item["id"] for item in result["catalog"]] == [
        "primary-message-injection",
        "subagent-message-injection",
    ]
    assert result["errors"] == {}


@pytest.mark.anyio
async def test_primary_example_defaults_to_lossless_multimodal_passthrough(
    tmp_path: Path,
) -> None:
    plugin_id = "primary-message-injection"
    source = _install_example(tmp_path, plugin_id)
    messages: list[dict[str, object]] = [
        {"role": "system", "content": "leading"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "inspect"},
                {
                    "type": "image",
                    "base64": "aW1hZ2U=",
                    "mime_type": "image/png",
                },
            ],
        },
        {"role": "system", "content": "late"},
    ]
    runtime = _runtime(
        tmp_path,
        owner_type="primary",
        plugin_id=plugin_id,
        transform_source=source,
        messages=messages,
    )

    await runtime.prepare()

    injected = runtime.messages_for("primary")
    assert [item["role"] for item in injected] == ["system", "assistant", "user"]
    assert injected[1]["content"][1] == {
        "type": "image",
        "base64": "aW1hZ2U=",
        "mime_type": "image/png",
    }
    assert runtime.request.messages[2]["role"] == "system"
    assert runtime.request.messages[1]["content"][0]["text"] == "inspect"
    await runtime.finish({"status": "completed"})


@pytest.mark.anyio
async def test_primary_custom_transform_runs_once(tmp_path: Path) -> None:
    plugin_id = "primary-message-injection"
    _install_example(tmp_path, plugin_id)
    runtime = _runtime(
        tmp_path,
        owner_type="primary",
        plugin_id=plugin_id,
        transform_source=(
            "async def transform_messages(messages, ctx, state, runtime):\n"
            "    ctx.vars['calls'] = ctx.vars.get('calls', 0) + 1\n"
            "    messages.append({'role': 'user', 'content': 'added'})\n"
            "    return messages\n"
        ),
        messages=[{"role": "user", "content": "original"}],
    )

    await runtime.prepare()

    assert runtime._variables["calls"] == 1
    assert [item["content"] for item in runtime.messages_for("primary")] == [
        "original",
        "added",
    ]
    await runtime.finish({"status": "completed"})


@pytest.mark.anyio
async def test_subagent_example_transforms_every_invocation_from_original_messages(
    tmp_path: Path,
) -> None:
    plugin_id = "subagent-message-injection"
    _install_example(tmp_path, plugin_id)
    runtime = _runtime(
        tmp_path,
        owner_type="subagent",
        plugin_id=plugin_id,
        transform_source=(
            "async def transform_messages(messages, ctx, state, runtime):\n"
            "    invocation = runtime.context['agent_shell_invocation']\n"
            "    invocation_id = invocation['id']\n"
            "    ctx.vars.setdefault('ids', []).append(invocation_id)\n"
            "    messages[0]['content'][0]['text'] = invocation_id\n"
            "    return messages\n"
        ),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "original"},
                {
                    "type": "audio",
                    "base64": "YXVkaW8=",
                    "mime_type": "audio/wav",
                },
            ],
        }],
    )
    middleware = runtime.middleware_for("child")[0]
    parent = runtime.root_context("child")["agent_shell_invocation"]

    async def invoke(index: int) -> list[object]:
        context = runtime.child_context("child", parent, f"task-{index}")
        result = await middleware.abefore_agent(
            {"messages": [HumanMessage(content=f"delegated-{index}")]},
            SimpleNamespace(context=context),
        )
        assert result is not None
        return result["messages"]

    results = await asyncio.gather(*(invoke(index) for index in range(4)))

    ids = [result[1]["content"][0]["text"] for result in results]
    assert len(set(ids)) == 4
    assert len(runtime._variables["ids"]) == 4
    assert all(isinstance(result[0], RemoveMessage) for result in results)
    assert all(result[1]["content"][1]["base64"] == "YXVkaW8=" for result in results)
    assert [result[-1].content for result in results] == [
        "delegated-0",
        "delegated-1",
        "delegated-2",
        "delegated-3",
    ]
    assert runtime.request.messages[0]["content"][0]["text"] == "original"
    await runtime.finish({"status": "completed"})


@pytest.mark.anyio
async def test_subagent_empty_transform_keeps_only_the_delegated_task(
    tmp_path: Path,
) -> None:
    plugin_id = "subagent-message-injection"
    _install_example(tmp_path, plugin_id)
    runtime = _runtime(
        tmp_path,
        owner_type="subagent",
        plugin_id=plugin_id,
        transform_source=(
            "async def transform_messages(messages, ctx, state, runtime):\n"
            "    return []\n"
        ),
        messages=[{"role": "user", "content": "original"}],
    )
    middleware = runtime.middleware_for("child")[0]
    context = runtime.root_context("child")

    result = await middleware.abefore_agent(
        {"messages": [HumanMessage(content="delegated")]},
        SimpleNamespace(context=context),
    )

    assert result is not None
    assert len(result["messages"]) == 2
    assert isinstance(result["messages"][0], RemoveMessage)
    assert result["messages"][1].content == "delegated"
    await runtime.finish({"status": "completed"})
