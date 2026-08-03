from __future__ import annotations

from agent_shell.automation.dependencies import dependency_state_path

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
            "/api/validation/draft",
            json={
                "target": {"kind": "automation", "type": "hook-workflow"},
                "payload": {"name": "Empty", "hooks": {}},
            },
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


def test_workflow_requires_current_plugin_dependency_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        write_automation_script(
            tmp_path,
            "image-reader",
            "async def run(ctx):\n    return None\n",
        )
        plugin = (
            tmp_path
            / "data"
            / "resources"
            / "automation_scripts"
            / "image-reader"
        )
        (plugin / "requirements.txt").write_text("Pillow>=11,<13\n", encoding="utf-8")
        catalog = client.get("/api/automation/scripts").json()["catalog"]
        pending = client.post(
            "/api/automation/hook-workflow",
            json={
                "name": "Image preparation",
                "hooks": {
                    "request_prepare": [
                        {"script_id": "image-reader", "config": {}}
                    ]
                },
            },
        )
        state_path = dependency_state_path(tmp_path / "runtime")
        state_path.parent.mkdir(parents=True)
        state_path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "platform": "windows-x64",
                    "status": "ready",
                    "plugins": {
                        "image-reader": {
                            "requirements_fingerprint": catalog[0][
                                "requirements_fingerprint"
                            ],
                            "status": "ready",
                            "error_code": "",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        ready = client.post(
            "/api/automation/hook-workflow",
            json={
                "name": "Image preparation",
                "hooks": {
                    "request_prepare": [
                        {"script_id": "image-reader", "config": {}}
                    ]
                },
            },
        )

    assert catalog[0]["dependency_status"] == "restart_required"
    assert pending.status_code == 422
    assert pending.json()["detail"]["validation"]["issues"][0]["code"] == (
        "automation.script_dependencies_restart_required"
    )
    assert ready.status_code == 200, ready.text
