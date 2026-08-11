from __future__ import annotations

from .support import *


def test_snapshot_freezes_workflow_filesystem_and_recursive_agent_permissions(
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
        main_permissions = client.post(
            "/api/blocks/filesystem-permissions",
            json={
                "name": "Main Agent file access",
                "permissions": [{"path": "/reports/**", "permission": "read-write"}],
                "tool_overrides": {"write_file": {"visible": True}},
            },
        ).json()
        subagent_permissions = client.post(
            "/api/blocks/filesystem-permissions",
            json={
                "name": "Subagent file access",
                "permissions": [{"path": "/reports/**", "permission": "read-only"}],
                "tool_overrides": {"write_file": {"visible": False}},
            },
        ).json()
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "reviewer-profile",
                name="reviewer",
                capability_overrides=[
                    {
                        "type": "filesystem-permissions",
                        "mode": "replace",
                        "block_id": subagent_permissions["id"],
                    }
                ],
            ),
        ).json()
        delegation = client.post(
            "/api/blocks/subagent", json={"name": "Review delegation"}
        ).json()
        main_agent = create_main_agent(client)
        updated_agent = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {
                        "type": "filesystem-permissions",
                        "block_id": main_permissions["id"],
                    },
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated_agent.status_code == 200, updated_agent.text
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
                "description": workflow["description"],
                "filesystem_id": second_filesystem["id"],
                "enabled": True,
            },
        )
        assert changed.status_code == 200, changed.text

        frozen_workflow = snapshot.workflow_by_name(workflow["name"])
        assert frozen_workflow is not None
        report, assembly = snapshot.resolve_main_agent(
            main_agent["id"],
            workflow_filesystem_id=frozen_workflow["filesystem_id"],
        )
        assert report.valid is True
        assert assembly is not None
        assert "filesystem" not in {
            item["type"] for item in updated_agent.json()["capability_refs"]
        }
        assert assembly.filesystem_mode == "configured-shared"
        assert assembly.references["filesystem"] == first_filesystem["id"]
        assert assembly.blocks["filesystem"]["id"] == first_filesystem["id"]
        assert (
            assembly.references["filesystem-permissions"] == main_permissions["id"]
        )
        child = assembly.subagent_nodes[subagent["id"]]
        assert child.filesystem_mode == "configured-shared"
        assert child.references["filesystem"] == first_filesystem["id"]
        assert child.blocks["filesystem"]["id"] == first_filesystem["id"]
        assert (
            child.references["filesystem-permissions"]
            == subagent_permissions["id"]
        )
        snapshot.close()

        next_snapshot = client.app.state.agent_runtime.capture()
        current_workflow = next_snapshot.workflow_by_name(workflow["name"])
        assert current_workflow is not None
        assert current_workflow["filesystem_id"] == second_filesystem["id"]
        next_snapshot.close()


def test_snapshot_keeps_agent_identity_on_one_committed_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        snapshot = client.app.state.agent_runtime.capture()
        renamed = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": "Renamed after capture",
                "capability_refs": main_agent["capability_refs"],
                "subagents": main_agent["subagents"],
            },
        )
        assert renamed.status_code == 200, renamed.text

        captured = snapshot.main_agent_by_name(main_agent["name"])
        assert captured is not None
        assert captured["id"] == main_agent["id"]
        assert snapshot.main_agent_by_name("Renamed after capture") is None
        snapshot.close()


def test_assembly_preserves_not_attached_middleware_semantics_per_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        summarization = client.post(
            "/api/blocks/summarization",
            json={"name": "Main summarization"},
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Review delegation"},
        ).json()
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "reviewer-profile",
                name="reviewer",
                capability_overrides=[
                    {
                        "type": "summarization",
                        "mode": "disabled",
                        "block_id": "",
                    }
                ],
            ),
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {
                        "type": "summarization",
                        "block_id": summarization["id"],
                    },
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        workflow = create_workflow(client, name="Middleware assembly")

        snapshot = client.app.state.agent_runtime.capture()
        report, assembly = snapshot.resolve_main_agent(
            main_agent["id"],
            workflow_filesystem_id=workflow["filesystem_id"],
        )
        snapshot.close()

    assert report.valid is True
    assert assembly is not None
    assert assembly.disabled_capabilities == frozenset(
        {"todo-list", "prompt-caching"}
    )
    child = assembly.subagent_nodes[subagent["id"]]
    assert child.disabled_capabilities == frozenset(
        {"todo-list", "summarization", "prompt-caching"}
    )
    assert "summarization" not in child.references
