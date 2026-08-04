from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime
from agent_shell.runtime.agent_runtime import AgentExecution
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import OutputProjector
from agent_shell.runtime.output_stream import V3EventNormalizer

from .support import config


def write_lifecycle_script(root: Path, script_id: str, source: str) -> None:
    folder = root / script_id
    folder.mkdir(parents=True)
    (folder / "script.json").write_text(
        json.dumps(
            {
                "api_version": 1,
                "id": script_id,
                "name": script_id,
                "description": "Automation control test script.",
                "triggers": ["lifecycle"],
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")


def make_runtime(
    tmp_path: Path, script_id: str, config_value: dict[str, str]
) -> AutomationRuntime:
    workflow = {
        "id": "workflow-id",
        "name": "Control workflow",
        "interval_seconds": 3600,
        "nodes": [{"script_id": script_id, "config": config_value}],
    }
    return AutomationRuntime(
        request_id="request-id",
        owners=[
            AutomationOwner(
                id="owner-id",
                type="primary",
                name="Primary",
                hook_workflow=None,
                lifecycle_workflow=workflow,
                mapped_paths={},
            )
        ],
        client_messages=[],
        scripts_dir=tmp_path / "scripts",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )


async def wait_for_file(path: Path) -> None:
    while not path.exists():
        await asyncio.sleep(0)


def test_finish_drains_the_running_lifecycle_node_without_cancelling_it(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    started = tmp_path / "started"
    release = tmp_path / "release"
    completed = tmp_path / "completed"
    cancelled = tmp_path / "cancelled"
    write_lifecycle_script(
        scripts,
        "drain-node",
        "import asyncio\n"
        "from pathlib import Path\n"
        "async def run(ctx):\n"
        "    Path(ctx.config['started']).touch()\n"
        "    try:\n"
        "        while not Path(ctx.config['release']).exists():\n"
        "            await asyncio.sleep(0)\n"
        "    except asyncio.CancelledError:\n"
        "        Path(ctx.config['cancelled']).touch()\n"
        "        raise\n"
        "    Path(ctx.config['completed']).touch()\n",
    )
    runtime = make_runtime(
        tmp_path,
        "drain-node",
        {
            "started": str(started),
            "release": str(release),
            "completed": str(completed),
            "cancelled": str(cancelled),
        },
    )

    async def scenario() -> None:
        await runtime.start()
        await asyncio.wait_for(wait_for_file(started), timeout=1)
        finishing = asyncio.create_task(runtime.finish({"status": "completed"}))
        await asyncio.sleep(0)
        assert not finishing.done()
        assert not cancelled.exists()
        release.touch()
        await asyncio.wait_for(finishing, timeout=1)

    asyncio.run(scenario())
    assert completed.exists()
    assert not cancelled.exists()


def test_graph_stop_request_takes_effect_after_the_node_returns(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    trigger = tmp_path / "trigger"
    completed = tmp_path / "completed"
    write_lifecycle_script(
        scripts,
        "stop-graph",
        "import asyncio\n"
        "from pathlib import Path\n"
        "async def run(ctx):\n"
        "    while not Path(ctx.config['trigger']).exists():\n"
        "        await asyncio.sleep(0)\n"
        "    ctx.request_graph_stop()\n"
        "    Path(ctx.config['completed']).touch()\n",
    )
    runtime = make_runtime(
        tmp_path,
        "stop-graph",
        {"trigger": str(trigger), "completed": str(completed)},
    )

    async def scenario() -> tuple[str, bool]:
        class BlockingRun:
            def __init__(self) -> None:
                self.pulling = asyncio.Event()
                self.exited = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
                self.exited = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                self.pulling.set()
                await asyncio.Event().wait()
                raise StopAsyncIteration

            async def output(self):
                return None

        class Graph:
            def __init__(self, run: BlockingRun) -> None:
                self.run = run

            async def astream_events(self, _input, *, config: dict, version: str):
                assert config == {"recursion_limit": 100}
                assert version == "v3"
                return self.run

        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"]["enabled"] = False
        settings["event_templates"]["lifecycle"] = {
            "enabled": True,
            "template": "{{phase}}:{{error_code}}",
        }
        run = BlockingRun()
        execution = AgentExecution(
            graph=Graph(run),
            input_state={"messages": [{"role": "user", "content": "run"}]},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
            automation=runtime,
        )
        stream = execution.stream_text()
        assert await anext(stream) == "start:"
        pending = asyncio.create_task(anext(stream))
        await asyncio.wait_for(run.pulling.wait(), timeout=1)
        trigger.touch()
        assert await asyncio.wait_for(pending, timeout=1) == (
            "error:automation_requested_graph_stop"
        )
        with pytest.raises(AgentRuntimeError) as captured:
            await anext(stream)
        return captured.value.code, run.exited

    code, stream_closed = asyncio.run(scenario())
    assert completed.exists()
    assert code == "automation_requested_graph_stop"
    assert stream_closed is True
