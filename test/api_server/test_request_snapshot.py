from __future__ import annotations

from .support import *


def test_snapshot_freezes_workflow_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        first_filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "First Workflow filesystem"},
        ).json()
        second_filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Second Workflow filesystem"},
        ).json()
        workflow = create_workflow(
            client,
            name="Frozen Workflow",
            filesystem_id=first_filesystem["id"],
        )

        snapshot = client.app.state.agent_runtime.capture()
        changed = client.put(
            f"/api/workflows/{workflow['id']}",
            json={
                "name": workflow["name"],
                "workflow_role": workflow["workflow_role"],
                "description": workflow["description"],
                "filesystem_id": second_filesystem["id"],
            },
        )
        assert changed.status_code == 200, changed.text

        frozen_workflow = snapshot.workflow_by_name(workflow["name"])
        assert frozen_workflow is not None
        assert frozen_workflow["filesystem_id"] == first_filesystem["id"]
        next_snapshot = client.app.state.agent_runtime.capture()
        current_workflow = next_snapshot.workflow_by_name(workflow["name"])
        assert current_workflow is not None
        assert current_workflow["filesystem_id"] == second_filesystem["id"]
