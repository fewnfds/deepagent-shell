from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_shell.automation.runtime import (
    AutomationContext,
    AutomationOwner,
    AutomationRuntime,
    AutomationVariables,
)
from agent_shell.automation.scripts import scan_automation_scripts


def write_script(
    root: Path,
    script_id: str,
    source: str,
    *,
    triggers: tuple[str, ...] = ("hook",),
) -> Path:
    folder = root / script_id
    folder.mkdir(parents=True)
    (folder / "script.json").write_text(
        json.dumps(
            {
                "api_version": 1,
                "id": script_id,
                "name": script_id,
                "description": "Runtime test script.",
                "triggers": list(triggers),
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")
    return folder


def test_script_scan_is_static_and_reports_invalid_entrypoints(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    marker = tmp_path / "imported.txt"
    write_script(
        scripts,
        "static-script",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n"
        "async def run(ctx):\n    return None\n",
    )
    write_script(
        scripts,
        "sync-script",
        "def run(ctx):\n    return None\n",
    )

    result = scan_automation_scripts(scripts)

    assert [item["id"] for item in result["catalog"]] == ["static-script"]
    assert result["errors"]["sync-script"]["message_key"] == (
        "resource.error.automationScript.asyncRunRequired"
    )
    assert not marker.exists()


def test_variables_are_json_copied_scoped_and_size_limited() -> None:
    request_values: dict[str, object] = {}
    agent_values: dict[str, object] = {}
    workflow_values: dict[str, object] = {}
    variables = AutomationVariables(request_values, agent_values, workflow_values)
    source = {"items": ["first"]}

    variables.set("request.shared", source)
    source["items"].append("outside")
    returned = variables.get("request.shared")
    returned["items"].append("caller")

    assert variables.get("request.shared") == {"items": ["first"]}
    variables.set("agent.local", 1)
    variables.set("workflow.local", 2)
    assert agent_values == {"local": 1}
    assert workflow_values == {"local": 2}
    with pytest.raises(ValueError, match="256 KiB"):
        variables.set("request.large", "x" * (256 * 1024))


def test_skill_preparation_is_limited_to_request_prepare(tmp_path: Path) -> None:
    owner = AutomationOwner(
        id="owner",
        type="primary",
        name="Primary",
        hook_workflow=None,
        lifecycle_workflow=None,
        mapped_paths={},
    )
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=[owner],
        client_messages=[],
        scripts_dir=tmp_path / "scripts",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )
    context = AutomationContext(
        runtime=runtime,
        owner=owner,
        workflow_type="lifecycle-workflow",
        workflow={"id": "workflow", "name": "Loop"},
        node={"script_id": "script", "config": {}},
        plugin_dir=tmp_path / "scripts" / "script",
        variables=AutomationVariables({}, {}, {}),
        hook="lifecycle",
        tick=0,
        messages=None,
        initial_files=None,
        terminal=None,
    )

    with pytest.raises(ValueError, match="request_prepare"):
        context.prepare_skill("alpha")


def test_hooks_lifecycle_and_owner_state_stay_request_local(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    mapped = tmp_path / "mapped"
    mapped.mkdir()
    write_script(
        scripts,
        "owner-hooks",
        "import json\n"
        "async def run(ctx):\n"
        "    hook = ctx.node['hook']\n"
        "    if hook == 'request_prepare':\n"
        "        shared = ctx.vars.get('request.prepare_count', 0) + 1\n"
        "        ctx.vars.set('request.prepare_count', shared)\n"
        "        ctx.vars.set('agent.prepare_count', 1)\n"
        "        ctx.messages.append({'role': 'user', 'content': f\"prepared:{ctx.agent['name']}:{shared}\"})\n"
        "        ctx.initial_files[f\"/{ctx.agent['id']}.txt\"] = ctx.agent['name']\n"
        "    elif hook == 'subagent_before_invoke':\n"
        "        count = ctx.vars.get('agent.invocations', 0) + 1\n"
        "        ctx.vars.set('agent.invocations', count)\n"
        "        ctx.messages.append({'role': 'assistant', 'content': f'invocation:{count}'})\n"
        "    elif hook == 'request_end':\n"
        "        target = ctx.paths.mapped['/mapped/'] / f\"end-{ctx.agent['id']}.json\"\n"
        "        target.write_text(json.dumps(dict(ctx.terminal)), encoding='utf-8')\n",
    )
    write_script(
        scripts,
        "owner-loop",
        "async def run(ctx):\n"
        "    count = ctx.vars.get('workflow.ticks', 0) + 1\n"
        "    ctx.vars.set('workflow.ticks', count)\n"
        "    target = ctx.paths.mapped['/mapped/'] / f\"tick-{ctx.agent['id']}.txt\"\n"
        "    target.write_text(str(count), encoding='utf-8')\n",
        triggers=("lifecycle",),
    )
    hook_workflow = {
        "id": "hook-id",
        "name": "Owner hooks",
        "hooks": {
            "request_prepare": [{"script_id": "owner-hooks", "config": {}}],
            "subagent_before_invoke": [
                {"script_id": "owner-hooks", "config": {}}
            ],
            "request_end": [{"script_id": "owner-hooks", "config": {}}],
        },
    }
    lifecycle_workflow = {
        "id": "loop-id",
        "name": "Owner loop",
        "interval_seconds": 0.01,
        "nodes": [{"script_id": "owner-loop", "config": {}}],
    }
    mapped_paths = {"/mapped/": mapped}
    owners = [
        AutomationOwner(
            id="primary-id",
            type="primary",
            name="Primary",
            hook_workflow=hook_workflow,
            lifecycle_workflow=lifecycle_workflow,
            mapped_paths=mapped_paths,
        ),
        AutomationOwner(
            id="subagent-id",
            type="subagent",
            name="Worker",
            hook_workflow=hook_workflow,
            lifecycle_workflow=lifecycle_workflow,
            mapped_paths=mapped_paths,
        ),
    ]
    runtime = AutomationRuntime(
        request_id="request-id",
        owners=owners,
        client_messages=[{"role": "user", "content": "original"}],
        scripts_dir=scripts,
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    async def scenario() -> None:
        await runtime.prepare()
        assert runtime.messages_for("primary-id")[-1]["content"] == (
            "prepared:Primary:1"
        )
        assert runtime.messages_for("subagent-id")[-1]["content"] == (
            "prepared:Worker:2"
        )
        delegated = [{"role": "user", "content": "delegated"}]
        first = await runtime.before_subagent_invoke("subagent-id", delegated)
        second = await runtime.before_subagent_invoke("subagent-id", delegated)
        assert first[-2:] == [
            {"role": "assistant", "content": "invocation:1"},
            delegated[0],
        ]
        assert second[-2:] == [
            {"role": "assistant", "content": "invocation:2"},
            delegated[0],
        ]
        await runtime.start()
        for _ in range(100):
            if all((mapped / f"tick-{owner.id}.txt").exists() for owner in owners):
                break
            await asyncio.sleep(0.005)
        assert len(runtime._tasks) == 2
        await runtime.finish({"status": "completed", "finish_reason": "stop"})

    asyncio.run(scenario())

    assert (mapped / "tick-primary-id.txt").read_text(encoding="utf-8")
    assert (mapped / "tick-subagent-id.txt").read_text(encoding="utf-8")
    assert json.loads((mapped / "end-primary-id.json").read_text(encoding="utf-8")) == {
        "status": "completed",
        "finish_reason": "stop",
    }
    assert not (tmp_path / "runtime" / "automation" / "request-id").exists()


def test_from_assembly_deduplicates_recursive_subagent_profiles(tmp_path: Path) -> None:
    edge_b = SimpleNamespace(target_key="B")
    edge_c = SimpleNamespace(target_key="C")
    node_b = SimpleNamespace(
        key="B",
        name="B",
        blocks={},
        hook_workflow=None,
        lifecycle_workflow=None,
        subagents=(edge_c,),
    )
    node_c = SimpleNamespace(
        key="C",
        name="C",
        blocks={},
        hook_workflow=None,
        lifecycle_workflow=None,
        subagents=(edge_b,),
    )
    assembly = SimpleNamespace(
        primary={"name": "A"},
        blocks={},
        hook_workflow=None,
        lifecycle_workflow=None,
        subagents=(edge_b, edge_c),
        subagent_nodes={"B": node_b, "C": node_c},
    )

    runtime = AutomationRuntime.from_assembly(
        assembly,
        [{"role": "user", "content": "input"}],
        primary_id="A",
        request_id="request",
        scripts_dir=tmp_path / "scripts",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )

    assert [owner.id for owner in runtime._owners] == ["A", "B", "C"]


def test_skill_overlay_is_request_only_and_persistent_mode_is_real(
    tmp_path: Path,
) -> None:
    skills = tmp_path / "skills"
    (skills / "alpha").mkdir(parents=True)
    (skills / "alpha" / "SKILL.md").write_text("original", encoding="utf-8")
    runtime = AutomationRuntime(
        request_id="skill-request",
        owners=[
            AutomationOwner(
                id="owner",
                type="primary",
                name="Primary",
                hook_workflow=None,
                lifecycle_workflow=None,
                mapped_paths={},
            )
        ],
        client_messages=[{"role": "user", "content": "input"}],
        scripts_dir=tmp_path / "scripts",
        skills_dir=skills,
        runtime_root=tmp_path / "runtime",
    )

    overlay = runtime.prepare_skill("owner", "alpha", mode="overlay")
    (overlay / "SKILL.md").write_text("overlay", encoding="utf-8")
    assert (skills / "alpha" / "SKILL.md").read_text(encoding="utf-8") == (
        "original"
    )
    assert runtime.effective_skills_dir("owner", ["alpha"]) == overlay.parent

    persistent = runtime.prepare_skill("owner", "alpha", mode="persistent")
    (persistent / "SKILL.md").write_text("persistent", encoding="utf-8")
    assert (skills / "alpha" / "SKILL.md").read_text(encoding="utf-8") == (
        "persistent"
    )

    asyncio.run(runtime.finish({"status": "completed"}))
    assert not overlay.parent.parent.exists()
