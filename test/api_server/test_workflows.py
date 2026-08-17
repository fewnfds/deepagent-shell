from __future__ import annotations

from .support import *


def test_workflow_runtime_boundaries_and_debug_retention_are_managed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        workflow = create_workflow(client, name="Managed boundaries")
        updated = client.put(
            f"/api/workflows/{workflow['id']}",
            json={
                "name": workflow["name"],
                "workflow_role": workflow["workflow_role"],
                "description": workflow["description"],
                "filesystem_id": workflow["filesystem_id"],
                "recursion_limit": 250,
                "execution_timeout_seconds": 900,
                "max_concurrency": 32,
                "enabled": True,
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["max_concurrency"] == 32

        current = client.get("/api/history-retention/workflow-debug")
        assert current.status_code == 200, current.text
        assert current.json()["retention_limit"] == 50
        saved = client.put(
            "/api/history-retention/workflow-debug",
            json={"retention_limit": 25},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["retention_limit"] == 25

        invalid = client.put(
            "/api/history-retention/workflow-debug",
            json={"retention_limit": 0},
        )
        assert invalid.status_code == 422


def test_workflow_event_output_is_a_reusable_component_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        defaults = client.get("/api/catalog").json()["editor_defaults"][
            "workflow_event_output"
        ]["default_value"]
        output = client.post(
            "/api/blocks/workflow-event-output",
            json={"name": "Public workflow events", **defaults},
        )
        assert output.status_code == 200, output.text
        workflow = create_workflow(client, name="Event Workflow")
        updated = client.put(
            f"/api/workflows/{workflow['id']}",
            json={
                **{key: workflow[key] for key in (
                    "name", "workflow_role", "description", "filesystem_id",
                    "workflow_prepare_id", "recursion_limit",
                    "execution_timeout_seconds", "max_concurrency", "enabled"
                )},
                "workflow_event_output_id": output.json()["id"],
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["workflow_event_output_id"] == output.json()["id"]
        protected = client.delete(
            f"/api/blocks/workflow-event-output/{output.json()['id']}"
        )
        assert protected.status_code == 409

    with make_client(tmp_path, monkeypatch) as client:
        saved = client.get(f"/api/workflows/{workflow['id']}").json()
        assert saved["workflow_event_output_id"] == output.json()["id"]


def test_workflow_roles_filter_management_and_public_model_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        assert client.get("/v1/models").json()["data"] == []

        created = create_workflow(
            client,
            name="Research Workflow",
        )
        child = create_workflow(
            client,
            name="Research Child",
            workflow_role="child",
        )
        assert client.get(f"/api/workflows/{created['id']}").json() == created
        assert client.get("/api/workflows").json() == [child, created]
        assert client.get(
            "/api/workflows?workflow_role=parent"
        ).json() == [created]
        assert client.get(
            "/api/workflows?workflow_role=child"
        ).json() == [child]
        assert [item["id"] for item in client.get("/v1/models").json()["data"]] == [
            "Research Workflow"
        ]
        assert created["workflow_role"] == "parent"
        assert child["workflow_role"] == "child"
        assert created["filesystem_id"]

        assert client.delete(f"/api/main-agents/{main_agent['id']}").json() == {
            "ok": True
        }

        disabled = client.put(
            f"/api/workflows/{created['id']}",
            json={
                "name": "Research Workflow",
                "workflow_role": "parent",
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
                "workflow_role": "parent",
                "description": "Duplicate.",
                "filesystem_id": existing["filesystem_id"],
                "enabled": True,
            },
        )
        removed_field = client.post(
            "/api/workflows",
            json={
                "name": "Legacy Workflow",
                "workflow_role": "parent",
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
                "workflow_role": "parent",
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
                "workflow_role": workflow["workflow_role"],
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
                        "config": {
                            "main_agent_id": main_agent["id"],
                            "defer": False,
                        },
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
                        "branch_key": None,
                        "dispatch_key": None,
                    },
                    {
                        "id": "agent-end",
                        "source": "agent",
                        "source_handle": "next",
                        "target": "end",
                        "target_handle": "in",
                        "branch_key": None,
                        "dispatch_key": None,
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
                "workflow_role": workflow["workflow_role"],
                "description": "Metadata changed without touching the graph.",
                "filesystem_id": workflow["filesystem_id"],
                "enabled": True,
            },
        )
        reloaded = client.get(graph_url)

    assert empty.status_code == 200
    assert empty.json()["definition"]["nodes"] == []
    assert [item["type"] for item in catalog.json()] == [
        "start",
        "agent",
        "condition-router",
        "task-dispatcher",
        "end",
    ]
    assert saved.status_code == 200, saved.text
    assert saved.json() == document
    assert metadata.status_code == 200, metadata.text
    assert reloaded.json() == document


def test_graph_save_rejects_background_action_as_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        child = create_workflow(client, name="Child", workflow_role="child")
        save_linear_workflow_graph(client, child, main_agent)
        graph_url = f"/api/workflows/{child['id']}/graph"
        document = client.get(graph_url).json()
        document["definition"]["nodes"].insert(
            1,
            {
                "id": "background-start",
                "type": "background-workflow-start",
                "type_version": 1,
                "config": {"child_workflow_id": child["id"]},
            },
        )
        document["definition"]["edges"][0]["target"] = "background-start"
        document["definition"]["edges"].insert(
            1,
            {
                "id": "background-agent",
                "source": "background-start",
                "source_handle": "next",
                "target": "agent",
                "target_handle": "in",
            },
        )

        response = client.put(graph_url, json=document)

    assert response.status_code == 422
    assert response.json()["detail"]["validation"]["issues"][0]["code"] == (
        "workflow.node_type_unsupported"
    )
