from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import AgentMiddleware

from agent_shell.automation.context import AutomationVariables
from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.automation.scripts import scan_automation_scripts
from agent_shell.runtime.errors import AgentRuntimeError


def write_plugin(
    root: Path,
    plugin_id: str,
    source: str,
    *,
    entrypoints: tuple[str, ...],
) -> Path:
    folder = root / plugin_id
    folder.mkdir(parents=True)
    (folder / "script.json").write_text(
        json.dumps(
            {
                "api_version": 2,
                "id": plugin_id,
                "name": plugin_id,
                "description": "Test plugin",
                "entrypoints": list(entrypoints),
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")
    return folder


def owner(
    plugin_id: str,
    *,
    interval: float | None = None,
    config: dict[str, object] | None = None,
) -> AutomationOwner:
    return AutomationOwner(
        id="owner",
        type="primary",
        name="Primary",
        automation={
            "plugins": [
                {
                    "plugin_id": plugin_id,
                    "enabled": True,
                    "config": config or {},
                }
            ],
            "lifecycle_interval_seconds": interval,
        },
        mapped_paths={},
    )


def runtime_for(
    tmp_path: Path,
    plugin_id: str,
    *,
    interval: float | None = None,
    config: dict[str, object] | None = None,
) -> AutomationRuntime:
    return AutomationRuntime(
        request_id="request-id",
        owners=[owner(plugin_id, interval=interval, config=config)],
        client_messages=[{"role": "user", "content": "original"}],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )


def test_plugin_scan_is_static_and_requires_the_v2_entrypoint_contract(
    tmp_path: Path,
) -> None:
    plugins = tmp_path / "plugins"
    marker = tmp_path / "imported.txt"
    write_plugin(
        plugins,
        "static-plugin",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
        "async def prepare(ctx):\n    return None\n",
        entrypoints=("prepare",),
    )
    invalid = plugins / "old-plugin"
    invalid.mkdir(parents=True)
    (invalid / "script.json").write_text(
        json.dumps(
            {
                "api_version": 1,
                "id": "old-plugin",
                "name": "Old",
                "description": "",
                "triggers": ["hook"],
            }
        ),
        encoding="utf-8",
    )
    (invalid / "main.py").write_text(
        "async def run(ctx):\n    return None\n",
        encoding="utf-8",
    )

    result = scan_automation_scripts(plugins)

    assert [item["id"] for item in result["catalog"]] == ["static-plugin"]
    assert "old-plugin" in result["errors"]
    assert not marker.exists()


@pytest.mark.anyio
async def test_prepare_middleware_and_immutable_request_share_request_local_ctx(
    tmp_path: Path,
) -> None:
    plugins = tmp_path / "plugins"
    folder = write_plugin(
        plugins,
        "context-plugin",
        "from .helper import EXTRA\n"
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class PluginMiddleware(AgentMiddleware):\n"
        "    state_schema = dict\n"
        "    tools = []\n"
        "    transformers = []\n"
        "    def __init__(self, ctx):\n        self.ctx = ctx\n"
        "    def before_agent(self, state, runtime):\n        return None\n"
        "    async def abefore_agent(self, state, runtime):\n"
        "        self.ctx.vars.set('agent.hook_seen', True)\n"
        "        return None\n"
        "    def before_model(self, state, runtime):\n        return None\n"
        "    async def abefore_model(self, state, runtime):\n        return None\n"
        "    def wrap_model_call(self, request, handler):\n        return handler(request)\n"
        "    async def awrap_model_call(self, request, handler):\n        return await handler(request)\n"
        "    def after_model(self, state, runtime):\n        return None\n"
        "    async def aafter_model(self, state, runtime):\n        return None\n"
        "    def wrap_tool_call(self, request, handler):\n        return handler(request)\n"
        "    async def awrap_tool_call(self, request, handler):\n        return await handler(request)\n"
        "    def after_agent(self, state, runtime):\n        return None\n"
        "    async def aafter_agent(self, state, runtime):\n        return None\n"
        "def create_middleware(ctx):\n    return PluginMiddleware(ctx)\n"
        "async def prepare(ctx):\n"
        "    assert ctx.request.messages[0]['content'] == 'original'\n"
        "    ctx.messages.append({'role': 'assistant', 'content': EXTRA})\n"
        "    ctx.vars.set('request.shared', {'value': 1})\n"
        "    ctx.vars.set('plugin.prepared', True)\n",
        entrypoints=("middleware", "prepare"),
    )
    (folder / "helper.py").write_text("EXTRA = 'prepared'\n", encoding="utf-8")
    runtime = runtime_for(tmp_path, "context-plugin")

    await runtime.prepare()
    middleware = runtime.middleware_for("owner")

    assert runtime.messages_for("owner") == [
        {"role": "user", "content": "original"},
        {"role": "assistant", "content": "prepared"},
    ]
    assert len(middleware) == 1
    item = middleware[0]
    assert type(item).__name__ == "PluginMiddleware"
    assert item.ctx.request is runtime.request
    assert item.ctx.vars.get("request.shared") == {"value": 1}
    assert item.ctx.vars.get("plugin.prepared") is True
    with pytest.raises(TypeError):
        item.ctx.request.messages[0]["content"] = "changed"
    with pytest.raises(AttributeError):
        item.ctx.request.messages.append({"role": "user", "content": "changed"})
    await item.abefore_agent({}, None)
    assert item.ctx.vars.get("agent.hook_seen") is True
    for hook in (
        "before_agent",
        "abefore_agent",
        "before_model",
        "abefore_model",
        "wrap_model_call",
        "awrap_model_call",
        "after_model",
        "aafter_model",
        "wrap_tool_call",
        "awrap_tool_call",
        "after_agent",
        "aafter_agent",
    ):
        assert hook in type(item).__dict__
    assert item.state_schema is dict
    assert item.tools == []
    assert item.transformers == []
    await runtime.finish({"status": "completed"})


def test_variables_are_json_copied_and_use_request_agent_plugin_scopes() -> None:
    variables = AutomationVariables({}, {}, {})
    source = {"items": ["first"]}
    variables.set("request.shared", source)
    source["items"].append("outside")
    returned = variables.get("request.shared")
    returned["items"].append("caller")
    variables.set("agent.local", 1)
    variables.set("plugin.local", 2)

    assert variables.get("request.shared") == {"items": ["first"]}
    assert variables.get("agent.local") == 1
    assert variables.get("plugin.local") == 2
    with pytest.raises(ValueError, match="plugin"):
        variables.set("workflow.old", True)
    with pytest.raises(ValueError, match="256 KiB"):
        variables.set("request.large", "x" * (256 * 1024 + 1))


@pytest.mark.anyio
async def test_lifecycle_drains_then_complete_runs_and_modules_are_cleaned(
    tmp_path: Path,
) -> None:
    started = tmp_path / "started"
    release = tmp_path / "release"
    completed = tmp_path / "completed"
    terminal = tmp_path / "terminal.json"
    write_plugin(
        tmp_path / "plugins",
        "lifecycle-plugin",
        "import asyncio\n"
        "from pathlib import Path\n"
        "async def lifecycle(ctx):\n"
        "    Path(ctx.config['started']).touch()\n"
        "    while not Path(ctx.config['release']).exists():\n        await asyncio.sleep(0)\n"
        "    ctx.vars.set('plugin.tick', ctx.tick)\n"
        "    Path(ctx.config['completed']).touch()\n"
        "async def complete(ctx):\n"
        "    Path(ctx.config['terminal']).write_text(str(dict(ctx.terminal)))\n",
        entrypoints=("lifecycle", "complete"),
    )
    runtime = runtime_for(
        tmp_path,
        "lifecycle-plugin",
        interval=3600,
        config={
            "started": str(started),
            "release": str(release),
            "completed": str(completed),
            "terminal": str(terminal),
        },
    )
    await runtime.prepare()
    await runtime.start()
    for _ in range(200):
        if started.exists():
            break
        await asyncio.sleep(0)
    finish = asyncio.create_task(runtime.finish({"status": "completed"}))
    await asyncio.sleep(0)
    assert not finish.done()
    release.touch()
    await finish

    assert completed.exists()
    assert "completed" in terminal.read_text(encoding="utf-8")
    assert not (tmp_path / "runtime" / "automation" / "request-id").exists()


@pytest.mark.anyio
async def test_prepare_validates_every_owner_message_view_before_construction(
    tmp_path: Path,
) -> None:
    write_plugin(
        tmp_path / "plugins",
        "invalid-message-plugin",
        "async def prepare(ctx):\n"
        "    ctx.messages.append({'role': 'tool', 'content': 'invalid'})\n",
        entrypoints=("prepare",),
    )
    runtime = runtime_for(tmp_path, "invalid-message-plugin")

    with pytest.raises(AgentRuntimeError) as error:
        await runtime.prepare()
    assert error.value.code == "input_message_role_unsupported"
    await runtime.finish({"status": "failed"})


def test_from_assembly_keeps_one_owner_per_recursive_subagent_profile(
    tmp_path: Path,
) -> None:
    empty = {"plugins": [], "lifecycle_interval_seconds": None}
    edge_b = SimpleNamespace(target_key="B")
    edge_c = SimpleNamespace(target_key="C")
    node_b = SimpleNamespace(
        key="B", name="B", blocks={}, automation=empty, subagents=(edge_c,)
    )
    node_c = SimpleNamespace(
        key="C", name="C", blocks={}, automation=empty, subagents=(edge_b,)
    )
    assembly = SimpleNamespace(
        primary={"name": "A"},
        blocks={},
        automation=empty,
        subagents=(edge_b, edge_c),
        subagent_nodes={"B": node_b, "C": node_c},
    )

    runtime = AutomationRuntime.from_assembly(
        assembly,
        [{"role": "user", "content": "input"}],
        primary_id="A",
        request_id="request",
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    assert [item.id for item in runtime._owners] == ["A", "B", "C"]
