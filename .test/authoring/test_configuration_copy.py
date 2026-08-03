from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from .reference_support import *


def test_primary_and_override_copy_create_server_ids_and_preserve_sources(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "copy-required", ("model", "filesystem", "output-mode")
    )
    override = client.post(
        "/api/subagent-overrides",
        json={"name": "Copy source override", "capability_overrides": []},
    ).json()
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Copy source Primary",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
            "subagents": [
                {
                    "name": "saved_worker",
                    "description": "Keeps the explicit override reference.",
                    "subagent_override_id": override["id"],
                }
            ],
        },
    ).json()

    primary_copy_response = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": "  Copied Primary  "},
    )
    override_copy_response = client.post(
        f"/api/subagent-overrides/{override['id']}/copy",
        json={"name": "Copied override"},
    )

    assert primary_copy_response.status_code == 200, primary_copy_response.text
    assert override_copy_response.status_code == 200, override_copy_response.text
    primary_copy = primary_copy_response.json()
    override_copy = override_copy_response.json()
    assert UUID(primary_copy["id"]) and primary_copy["id"] != primary["id"]
    assert UUID(override_copy["id"]) and override_copy["id"] != override["id"]
    assert primary_copy["name"] == "Copied Primary"
    assert override_copy["name"] == "Copied override"
    assert primary_copy["capability_refs"] == primary["capability_refs"]
    assert primary_copy["subagents"] == primary["subagents"]
    assert override_copy["capability_overrides"] == override["capability_overrides"]
    assert client.get(f"/api/primary-agents/{primary['id']}").json() == primary
    assert client.get(f"/api/subagent-overrides/{override['id']}").json() == override


def test_component_bulk_delete_is_atomic_when_any_target_is_referenced(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "bulk-required", ("model", "filesystem", "output-mode")
    )
    second = client.post(
        "/api/blocks/filesystem",
        json=block_payload("filesystem", "bulk-second-filesystem"),
    ).json()
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Bulk owner",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
        },
    ).json()
    ids = [required["filesystem"]["id"], second["id"]]

    blocked = client.post("/api/blocks/filesystem/delete", json={"ids": ids})
    assert blocked.status_code == 409
    assert all(
        client.get(f"/api/blocks/filesystem/{item_id}").status_code == 200
        for item_id in ids
    )

    assert client.delete(f"/api/primary-agents/{primary['id']}").status_code == 200
    deleted = client.post("/api/blocks/filesystem/delete", json={"ids": ids})
    assert deleted.json() == {"deleted": 2}
    assert client.get("/api/blocks/filesystem").json() == []


def test_agent_configuration_bulk_delete_uses_one_command_per_category(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "bulk-agents", ("model", "filesystem", "output-mode")
    )
    primary_ids = []
    override_ids = []
    for index in range(2):
        primary_ids.append(client.post(
            "/api/primary-agents",
            json={
                "name": f"Bulk Primary {index}",
                "capability_refs": references(
                    required, ("model", "filesystem", "output-mode")
                ),
            },
        ).json()["id"])
        override_ids.append(client.post(
            "/api/subagent-overrides",
            json={
                "name": f"Bulk override {index}",
                "capability_overrides": [],
            },
        ).json()["id"])

    assert client.post(
        "/api/primary-agents/delete", json={"ids": primary_ids}
    ).json() == {"deleted": 2}
    assert client.post(
        "/api/subagent-overrides/delete", json={"ids": override_ids}
    ).json() == {"deleted": 2}
    assert client.get("/api/primary-agents").json() == []
    assert client.get("/api/subagent-overrides").json() == []


def test_agent_config_copy_rejects_duplicate_names_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "duplicate-copy", ("model", "filesystem", "output-mode")
    )
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Duplicate Primary",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
        },
    ).json()
    override = client.post(
        "/api/subagent-overrides",
        json={"name": "Duplicate override", "capability_overrides": []},
    ).json()

    primary_copy = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": primary["name"]},
    )
    override_copy = client.post(
        f"/api/subagent-overrides/{override['id']}/copy",
        json={"name": override["name"]},
    )

    assert primary_copy.status_code == 409
    assert override_copy.status_code == 409
    assert client.get("/api/primary-agents").json() == [primary]
    assert client.get("/api/subagent-overrides").json() == [override]


def test_agent_config_copy_returns_not_found_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    primary_copy = client.post(
        "/api/primary-agents/missing/copy", json={"name": "Missing Primary copy"}
    )
    override_copy = client.post(
        "/api/subagent-overrides/missing/copy",
        json={"name": "Missing override copy"},
    )

    assert primary_copy.status_code == 404
    assert override_copy.status_code == 404
    assert client.get("/api/primary-agents").json() == []
    assert client.get("/api/subagent-overrides").json() == []


def test_agent_config_copy_revalidates_invalid_stored_sources_before_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "invalid-copy", ("model", "filesystem", "output-mode")
    )
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Invalid stored Primary",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
        },
    ).json()
    override = client.post(
        "/api/subagent-overrides",
        json={"name": "Invalid stored override", "capability_overrides": []},
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        primary_payload = json.loads(
            connection.execute(
                "SELECT payload FROM primary_agents WHERE id = ?", (primary["id"],)
            ).fetchone()[0]
        )
        primary_payload["capability_refs"][0]["block_id"] = "missing-block"
        override_payload = {
            "capability_overrides": [
                {"type": "model", "mode": "replace", "block_id": "missing-block"}
            ]
        }
        connection.execute(
            "UPDATE primary_agents SET payload = ? WHERE id = ?",
            (json.dumps(primary_payload), primary["id"]),
        )
        connection.execute(
            "UPDATE subagent_overrides SET payload = ? WHERE id = ?",
            (json.dumps(override_payload), override["id"]),
        )

    before_primary = client.get(f"/api/primary-agents/{primary['id']}").json()
    before_override = client.get(f"/api/subagent-overrides/{override['id']}").json()
    primary_copy = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": "Rejected Primary copy"},
    )
    override_copy = client.post(
        f"/api/subagent-overrides/{override['id']}/copy",
        json={"name": "Rejected override copy"},
    )

    assert primary_copy.status_code == 422
    assert override_copy.status_code == 422
    assert client.get(f"/api/primary-agents/{primary['id']}").json() == before_primary
    assert client.get(f"/api/subagent-overrides/{override['id']}").json() == before_override
    assert len(client.get("/api/primary-agents").json()) == 1
    assert len(client.get("/api/subagent-overrides").json()) == 1
