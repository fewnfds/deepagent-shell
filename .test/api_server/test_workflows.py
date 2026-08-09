from __future__ import annotations

from .support import *


def test_workflow_crud_owns_model_publication_and_main_agent_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client, create_workflow=False)
        assert client.get("/v1/models").json()["data"] == []

        created = create_workflow_for_agent(
            client,
            main_agent,
            name="Research Workflow",
        )
        assert client.get(f"/api/workflows/{created['id']}").json() == created
        assert client.get("/api/workflows").json() == [created]
        assert [item["id"] for item in client.get("/v1/models").json()["data"]] == [
            "Research Workflow"
        ]

        blocked = client.delete(f"/api/main-agents/{main_agent['id']}")
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "main_agent_referenced_by_workflow"

        disabled = client.put(
            f"/api/workflows/{created['id']}",
            json={
                "name": "Research Workflow",
                "description": "Disabled test Workflow.",
                "main_agent_id": main_agent["id"],
                "enabled": False,
            },
        )
        assert disabled.status_code == 200, disabled.text
        assert client.get("/v1/models").json()["data"] == []

        deleted = client.delete(f"/api/workflows/{created['id']}")
        assert deleted.json() == {"ok": True}
        assert client.delete(f"/api/main-agents/{main_agent['id']}").json() == {
            "ok": True
        }


def test_workflow_rejects_duplicate_names_and_missing_main_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client, create_workflow=False)
        create_workflow_for_agent(client, main_agent, name="Unique Workflow")
        duplicate = client.post(
            "/api/workflows",
            json={
                "name": "Unique Workflow",
                "description": "Duplicate.",
                "main_agent_id": main_agent["id"],
                "enabled": True,
            },
        )
        missing = client.post(
            "/api/workflows",
            json={
                "name": "Missing Agent Workflow",
                "description": "Invalid reference.",
                "main_agent_id": "missing-agent",
                "enabled": True,
            },
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "workflow_name_conflict"
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "workflow_main_agent_not_found"
