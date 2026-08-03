from __future__ import annotations

from .support import *


def test_automation_crud_validation_and_reference_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "open-script",
            "async def run(ctx):\n    ctx.vars.set('request.seen', True)\n",
            triggers=("hook", "lifecycle"),
        )
        scripts = client.get("/api/automation/scripts")
        invalid = client.post(
            "/api/automation/hook-workflow/validate",
            json={"name": "Empty", "hooks": {}},
        )
        hook = create_hook_workflow(
            client,
            "Request preparation",
            request_prepare=[{"script_id": "open-script", "config": {}}],
        )
        lifecycle = client.post(
            "/api/automation/lifecycle-workflow",
            json={
                "name": "Refresh files",
                "interval_seconds": 2,
                "nodes": [{"script_id": "open-script", "config": {}}],
            },
        )
        copied = client.post(
            f"/api/automation/hook-workflow/{hook['id']}/copy",
            json={"name": "Request preparation copy"},
        )
        primary = create_primary(client)
        attached = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": primary["capability_refs"],
                "subagents": [],
                "automation": {
                    "hook_workflow_id": hook["id"],
                    "lifecycle_workflow_id": lifecycle.json()["id"],
                },
            },
        )
        removed = client.delete(
            f"/api/automation/hook-workflow/{hook['id']}"
        )
        stored_primary = client.get(f"/api/primary-agents/{primary['id']}")

    assert scripts.status_code == 200
    assert [item["id"] for item in scripts.json()["catalog"]] == ["open-script"]
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert lifecycle.status_code == 200, lifecycle.text
    assert copied.status_code == 200, copied.text
    assert copied.json()["name"] == "Request preparation copy"
    assert attached.status_code == 200, attached.text
    assert removed.status_code == 200
    assert stored_primary.json()["automation"] == {
        "hook_workflow_id": "",
        "lifecycle_workflow_id": lifecycle.json()["id"],
    }


def test_repository_validation_rechecks_changed_script_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "mutable-script",
            "async def run(ctx):\n    return None\n",
        )
        workflow = create_hook_workflow(
            client,
            "Stored workflow",
            request_prepare=[{"script_id": "mutable-script", "config": {}}],
        )
        stopped = client.post("/api/api-server/stop")
        script_path = (
            tmp_path
            / "data"
            / "resources"
            / "automation_scripts"
            / "mutable-script"
            / "main.py"
        )
        script_path.unlink()
        started = client.post("/api/api-server/start")

    assert workflow["id"]
    assert stopped.status_code == 200
    assert started.status_code == 422
    issues = started.json()["detail"]["validation"]["issues"]
    assert any(
        issue["owner_id"] == workflow["id"]
        and issue["code"] == "automation.script_invalid"
        for issue in issues
    )
