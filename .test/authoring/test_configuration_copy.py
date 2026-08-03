from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from .reference_support import *


def test_primary_and_subagent_copy_create_server_ids_and_preserve_sources(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "copy-required", ("model", "filesystem", "output-mode")
    )
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload("Copy source Subagent", name="saved_worker"),
    ).json()
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Copy source Primary",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
            "subagents": [{"subagent_id": subagent["id"]}],
        },
    ).json()

    primary_copy_response = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": "  Copied Primary  "},
    )
    subagent_copy_response = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": "Copied Subagent"},
    )

    assert primary_copy_response.status_code == 200, primary_copy_response.text
    assert subagent_copy_response.status_code == 200, subagent_copy_response.text
    primary_copy = primary_copy_response.json()
    subagent_copy = subagent_copy_response.json()
    assert UUID(primary_copy["id"]) and primary_copy["id"] != primary["id"]
    assert UUID(subagent_copy["id"]) and subagent_copy["id"] != subagent["id"]
    assert primary_copy["name"] == "Copied Primary"
    assert subagent_copy["component_name"] == "Copied Subagent"
    assert subagent_copy["name"] == subagent["name"]
    assert primary_copy["capability_refs"] == primary["capability_refs"]
    assert primary_copy["subagents"] == primary["subagents"]
    assert subagent_copy["settings"] == subagent["settings"]
    assert client.get(f"/api/primary-agents/{primary['id']}").json() == primary
    assert client.get(f"/api/subagents/{subagent['id']}").json() == subagent


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
    subagent_ids = []
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
        subagent_ids.append(client.post(
            "/api/subagents",
            json=subagent_payload(
                f"Bulk Subagent {index}",
                name=f"bulk_worker_{index}",
            ),
        ).json()["id"])

    assert client.post(
        "/api/primary-agents/delete", json={"ids": primary_ids}
    ).json() == {"deleted": 2}
    assert client.post(
        "/api/subagents/delete", json={"ids": subagent_ids}
    ).json() == {"deleted": 2}
    assert client.get("/api/primary-agents").json() == []
    assert client.get("/api/subagents").json() == []


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
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload("Duplicate Subagent", name="duplicate_worker"),
    ).json()

    primary_copy = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": primary["name"]},
    )
    subagent_copy = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": subagent["component_name"]},
    )

    assert primary_copy.status_code == 409
    assert subagent_copy.status_code == 409
    assert client.get("/api/primary-agents").json() == [primary]
    assert client.get("/api/subagents").json() == [subagent]


def test_agent_config_copy_returns_not_found_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    primary_copy = client.post(
        "/api/primary-agents/missing/copy", json={"name": "Missing Primary copy"}
    )
    subagent_copy = client.post(
        "/api/subagents/missing/copy",
        json={"component_name": "Missing Subagent copy"},
    )

    assert primary_copy.status_code == 404
    assert subagent_copy.status_code == 404
    assert client.get("/api/primary-agents").json() == []
    assert client.get("/api/subagents").json() == []


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
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload("Invalid stored Subagent", name="invalid_worker"),
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        primary_payload = json.loads(
            connection.execute(
                "SELECT payload FROM primary_agents WHERE id = ?", (primary["id"],)
            ).fetchone()[0]
        )
        primary_payload["capability_refs"][0]["block_id"] = "missing-block"
        subagent_payload_json = json.loads(
            connection.execute(
                "SELECT payload FROM subagents WHERE id = ?", (subagent["id"],)
            ).fetchone()[0]
        )
        subagent_payload_json["settings"]["capability_overrides"] = [
            {"type": "model", "mode": "replace", "block_id": "missing-block"}
        ]
        connection.execute(
            "UPDATE primary_agents SET payload = ? WHERE id = ?",
            (json.dumps(primary_payload), primary["id"]),
        )
        connection.execute(
            "UPDATE subagents SET payload = ? WHERE id = ?",
            (json.dumps(subagent_payload_json), subagent["id"]),
        )

    before_primary = client.get(f"/api/primary-agents/{primary['id']}").json()
    before_subagent = client.get(f"/api/subagents/{subagent['id']}").json()
    primary_copy = client.post(
        f"/api/primary-agents/{primary['id']}/copy",
        json={"name": "Rejected Primary copy"},
    )
    subagent_copy = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": "Rejected Subagent copy"},
    )

    assert primary_copy.status_code == 422
    assert subagent_copy.status_code == 422
    assert client.get(f"/api/primary-agents/{primary['id']}").json() == before_primary
    assert client.get(f"/api/subagents/{subagent['id']}").json() == before_subagent
    assert len(client.get("/api/primary-agents").json()) == 1
    assert len(client.get("/api/subagents").json()) == 1
