from __future__ import annotations

from .support import *


def test_workflow_crud_publishes_enabled_tbd_entries_without_main_agent_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        assert client.get("/v1/models").json()["data"] == []

        created = create_workflow(
            client,
            name="Research Workflow",
        )
        assert client.get(f"/api/workflows/{created['id']}").json() == created
        assert client.get("/api/workflows").json() == [created]
        assert [item["id"] for item in client.get("/v1/models").json()["data"]] == [
            "Research Workflow"
        ]
        assert created["filesystem_id"]

        assert client.delete(f"/api/main-agents/{main_agent['id']}").json() == {
            "ok": True
        }

        disabled = client.put(
            f"/api/workflows/{created['id']}",
            json={
                "name": "Research Workflow",
                "description": "Disabled test Workflow.",
                "filesystem_id": created["filesystem_id"],
                "enabled": False,
            },
        )
        assert disabled.status_code == 200, disabled.text
        assert client.get("/v1/models").json()["data"] == []

        deleted = client.delete(f"/api/workflows/{created['id']}")
        assert deleted.json() == {"ok": True}


def test_workflow_rejects_duplicate_names_and_removed_main_agent_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        existing = create_workflow(client, name="Unique Workflow")
        duplicate = client.post(
            "/api/workflows",
            json={
                "name": "Unique Workflow",
                "description": "Duplicate.",
                "filesystem_id": existing["filesystem_id"],
                "enabled": True,
            },
        )
        removed_field = client.post(
            "/api/workflows",
            json={
                "name": "Legacy Workflow",
                "description": "Rejected legacy shape.",
                "main_agent_id": "missing-agent",
                "filesystem_id": existing["filesystem_id"],
                "enabled": True,
            },
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "workflow_name_conflict"
    assert removed_field.status_code == 422
    assert removed_field.json()["detail"]["code"] == "workflow_invalid"


def test_workflow_requires_existing_filesystem_and_protects_its_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        missing = client.post(
            "/api/workflows",
            json={
                "name": "Missing Filesystem",
                "description": "Rejected reference.",
                "filesystem_id": "00000000-0000-0000-0000-000000000000",
                "enabled": True,
            },
        )
        first = client.post(
            "/api/blocks/filesystem", json={"name": "First shared workspace"}
        ).json()
        second = client.post(
            "/api/blocks/filesystem", json={"name": "Second shared workspace"}
        ).json()
        workflow = create_workflow(
            client,
            name="Protected Workflow",
            filesystem_id=first["id"],
        )
        protected = client.delete(f"/api/blocks/filesystem/{first['id']}")
        changed = client.put(
            f"/api/workflows/{workflow['id']}",
            json={
                "name": workflow["name"],
                "description": workflow["description"],
                "filesystem_id": second["id"],
                "enabled": workflow["enabled"],
            },
        )
        released = client.delete(f"/api/blocks/filesystem/{first['id']}")
        client.delete(f"/api/workflows/{workflow['id']}")
        final_delete = client.delete(f"/api/blocks/filesystem/{second['id']}")

    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "workflow_filesystem_not_found"
    assert protected.status_code == 409
    assert protected.json()["detail"]["code"] == "configuration_referenced"
    assert changed.status_code == 200, changed.text
    assert changed.json()["filesystem_id"] == second["id"]
    assert released.json() == {"ok": True}
    assert final_delete.json() == {"ok": True}


def test_workflow_graph_catalog_save_and_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        workflow = create_workflow(client, name="Canvas Workflow")
        graph_url = f"/api/workflows/{workflow['id']}/graph"

        empty = client.get(graph_url)
        catalog = client.get("/api/workflow-node-catalog")
        document = {
            "definition": {
                "schema_version": 1,
                "state_contract": "agent-shell.workflow.agent-invocations.v1",
                "nodes": [
                    {"id": "start", "type": "start", "type_version": 1, "config": {}},
                    {
                        "id": "agent",
                        "type": "agent",
                        "type_version": 1,
                        "config": {"main_agent_id": main_agent["id"]},
                    },
                    {"id": "end", "type": "end", "type_version": 1, "config": {}},
                ],
                "edges": [
                    {
                        "id": "start-agent",
                        "source": "start",
                        "source_handle": "next",
                        "target": "agent",
                        "target_handle": "in",
                    },
                    {
                        "id": "agent-end",
                        "source": "agent",
                        "source_handle": "next",
                        "target": "end",
                        "target_handle": "in",
                    },
                ],
            },
            "layout": {
                "nodes": {
                    "start": {"x": 80, "y": 160},
                    "agent": {"x": 360, "y": 160},
                    "end": {"x": 640, "y": 160},
                },
                "viewport": {"x": 10, "y": 20, "zoom": 1.25},
            },
        }
        saved = client.put(graph_url, json=document)
        metadata = client.put(
            f"/api/workflows/{workflow['id']}",
            json={
                "name": workflow["name"],
                "description": "Metadata changed without touching the graph.",
                "filesystem_id": workflow["filesystem_id"],
                "enabled": True,
            },
        )
        reloaded = client.get(graph_url)

    assert empty.status_code == 200
    assert empty.json()["definition"]["nodes"] == []
    assert [item["type"] for item in catalog.json()] == ["start", "agent", "end"]
    assert saved.status_code == 200, saved.text
    assert saved.json() == document
    assert metadata.status_code == 200, metadata.text
    assert reloaded.json() == document
