from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.automation.scripts import scan_automation_scripts
from agent_shell.runtime.errors import AgentRuntimeError

from .automation_support import runtime_for, write_plugin


def test_plugin_scan_is_static_and_requires_the_v3_entrypoint_contract(
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
    assert result["catalog"][0]["config_schema"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    assert "old-plugin" in result["errors"]
    assert not marker.exists()


@pytest.mark.parametrize(
    "config_schema",
    [
        {
            "type": "object",
            "properties": {
                "items": {"type": "array", "title": "Items"},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "title": "Mode",
                    "enum": [1, 2],
                },
            },
            "additionalProperties": False,
        },
    ],
)
def test_plugin_scan_rejects_unrenderable_config_schema(
    tmp_path: Path,
    config_schema: dict[str, object],
) -> None:
    write_plugin(
        tmp_path / "plugins",
        "invalid-schema",
        "async def prepare(ctx):\n    return None\n",
        entrypoints=("prepare",),
        config_schema=config_schema,
    )

    result = scan_automation_scripts(tmp_path / "plugins")

    assert result["catalog"] == []
    assert result["errors"]["invalid-schema"]["message_key"] == (
        "resource.error.automationScript.manifestInvalid"
    )


@pytest.mark.anyio
async def test_prepare_and_middleware_share_only_immutable_request_context(
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
        "        return {'shared_vars': {'hook_seen': True}}\n"
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
        "    assert ctx.request.messages[0]['content'] == 'original'\n",
        entrypoints=("middleware", "prepare"),
    )
    (folder / "helper.py").write_text("EXTRA = 'prepared'\n", encoding="utf-8")
    runtime = runtime_for(tmp_path, "context-plugin")

    await runtime.prepare()
    middleware = runtime.middleware_for("owner")

    assert len(middleware) == 1
    item = middleware[0]
    assert type(item).__name__ == "PluginMiddleware"
    assert item.ctx.request is runtime.request
    assert not hasattr(item.ctx, "vars")
    with pytest.raises(TypeError):
        item.ctx.request.messages[0]["content"] = "changed"
    with pytest.raises(AttributeError):
        item.ctx.request.messages.append({"role": "user", "content": "changed"})
    assert await item.abefore_agent({}, None) == {
        "shared_vars": {"hook_seen": True}
    }
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


@pytest.mark.anyio
async def test_no_binding_keeps_client_messages_out_of_owner_activity(
    tmp_path: Path,
) -> None:
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=[
            AutomationOwner(
                id="main_agent",
                type="main_agent",
                name="Main Agent",
                automation={"hooks": [], "periodic": []},
                mapped_paths={},
            ),
            AutomationOwner(
                id="child",
                type="subagent",
                name="Child",
                automation={"hooks": [], "periodic": []},
                mapped_paths={},
            ),
        ],
        client_messages=[{"role": "user", "content": "original"}],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    await runtime.prepare()

    assert runtime.request.messages[0]["content"] == "original"
    await runtime.finish({"status": "completed"})


@pytest.mark.anyio
async def test_middleware_bindings_write_shared_vars_through_state_updates(
    tmp_path: Path,
) -> None:
    write_plugin(
        tmp_path / "plugins",
        "shared-vars-plugin",
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class Capture(AgentMiddleware):\n"
        "    def __init__(self, ctx):\n        self.ctx = ctx\n"
        "    async def abefore_agent(self, state, runtime):\n"
        "        previous = state.get('shared_vars', {}).get('first_called', False)\n"
        "        return {'shared_vars': {'second_saw_first': previous}}\n"
        "def create_middleware(ctx):\n    return Capture(ctx)\n",
        entrypoints=("middleware",),
    )
    binding = {
        "plugin_id": "shared-vars-plugin",
        "enabled": True,
        "config": {},
    }
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=[
            AutomationOwner(
                id="owner",
                type="main_agent",
                name="Main Agent",
                automation={"hooks": [binding, binding], "periodic": []},
                mapped_paths={},
            )
        ],
        client_messages=[{"role": "user", "content": "original"}],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    first, second = runtime.middleware_for("owner")
    assert first.name != second.name
    assert not hasattr(first.ctx, "vars")
    assert await second.abefore_agent(
        {"shared_vars": {"first_called": True}}, None
    ) == {"shared_vars": {"second_saw_first": True}}


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
        "    Path(ctx.config['completed']).touch()\n"
        "async def complete(ctx):\n"
        "    Path(ctx.config['terminal']).write_text(str(dict(ctx.terminal)))\n",
        entrypoints=("lifecycle", "complete"),
        config_schema={
            "type": "object",
            "properties": {
                name: {"type": "string", "title": name}
                for name in ("started", "release", "completed", "terminal")
            },
            "required": ["started", "release", "completed", "terminal"],
            "additionalProperties": False,
        },
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
async def test_periodic_bindings_have_independent_tasks_and_failure_boundaries(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "healthy-tick"
    write_plugin(
        tmp_path / "plugins",
        "periodic-plugin",
        "from pathlib import Path\n"
        "async def lifecycle(ctx):\n"
        "    if ctx.config.get('fail'):\n        raise RuntimeError('stopped')\n"
        "    Path(ctx.config['marker']).write_text(f\"{ctx.plugin['kind']}:{ctx.tick}\")\n",
        entrypoints=("lifecycle",),
        config_schema={
            "type": "object",
            "properties": {
                "fail": {"type": "boolean", "title": "fail"},
                "marker": {"type": "string", "title": "marker"},
            },
            "additionalProperties": False,
        },
    )
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=[
            AutomationOwner(
                id="owner",
                type="main_agent",
                name="Main Agent",
                automation={
                    "hooks": [],
                    "periodic": [
                        {
                            "plugin_id": "periodic-plugin",
                            "enabled": True,
                            "config": {"fail": True},
                            "interval_seconds": 0.1,
                        },
                        {
                            "plugin_id": "periodic-plugin",
                            "enabled": True,
                            "config": {"marker": str(marker)},
                            "interval_seconds": 3600,
                        },
                    ],
                },
                mapped_paths={},
            )
        ],
        client_messages=[{"role": "user", "content": "original"}],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    await runtime.start()
    for _ in range(200):
        if marker.exists():
            break
        await asyncio.sleep(0)
    await runtime.finish({"status": "completed"})

    assert marker.read_text(encoding="utf-8") == "periodic:0"


@pytest.mark.anyio
async def test_prepare_does_not_expose_a_message_injection_buffer(
    tmp_path: Path,
) -> None:
    write_plugin(
        tmp_path / "plugins",
        "legacy-message-plugin",
        "async def prepare(ctx):\n"
        "    ctx.messages.append({'role': 'user', 'content': 'legacy'})\n",
        entrypoints=("prepare",),
    )
    runtime = runtime_for(tmp_path, "legacy-message-plugin")

    with pytest.raises(AgentRuntimeError) as error:
        await runtime.prepare()
    assert error.value.code == "automation_plugin_failed"
    await runtime.finish({"status": "failed"})


def test_from_assembly_keeps_main_and_direct_subagent_owners(
    tmp_path: Path,
) -> None:
    empty = {"hooks": [], "periodic": []}
    from agent_shell.validation.service import (
        ResolvedSubagent,
        ResolvedSubagentEdge,
        StaticAssembly,
    )

    node_b = ResolvedSubagent(
        key="B",
        component_name="B",
        name="B",
        description="B",
        references={},
        blocks={},
        filesystem_mode="default-shared",
        automation=empty,
    )
    node_c = ResolvedSubagent(
        key="C",
        component_name="C",
        name="C",
        description="C",
        references={},
        blocks={},
        filesystem_mode="default-shared",
        automation=empty,
    )
    assembly = StaticAssembly(
        main_agent={"component_name": "A", "name": "A"},
        references={},
        blocks={},
        filesystem_mode="default-shared",
        automation=empty,
        subagents=(
            ResolvedSubagentEdge(target_key="B"),
            ResolvedSubagentEdge(target_key="C"),
        ),
        subagent_nodes={"B": node_b, "C": node_c},
    )

    runtime = AutomationRuntime.from_assembly(
        assembly,
        [{"role": "user", "content": "input"}],
        main_agent_id="A",
        request_id="request",
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    assert [item.id for item in runtime._owners] == ["A", "B", "C"]
