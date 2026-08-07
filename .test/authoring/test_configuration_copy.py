from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from .reference_support import *


def test_main_agent_and_subagent_copy_create_server_ids_and_preserve_sources(
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
    main_agent = client.post(
        "/api/main-agents",
        json={
            "name": "Copy source Main Agent",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
            "subagents": [{"subagent_id": subagent["id"]}],
        },
    ).json()

    main_agent_copy_response = client.post(
        f"/api/main-agents/{main_agent['id']}/copy",
        json={"name": "  Copied Main Agent  "},
    )
    subagent_copy_response = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": "Copied Subagent"},
    )

    assert main_agent_copy_response.status_code == 200, main_agent_copy_response.text
    assert subagent_copy_response.status_code == 200, subagent_copy_response.text
    main_agent_copy = main_agent_copy_response.json()
    subagent_copy = subagent_copy_response.json()
    assert UUID(main_agent_copy["id"]) and main_agent_copy["id"] != main_agent["id"]
    assert UUID(subagent_copy["id"]) and subagent_copy["id"] != subagent["id"]
    assert main_agent_copy["name"] == "Copied Main Agent"
    assert main_agent_copy["public_id"] == "agent-copied-main-agent"
    assert subagent_copy["component_name"] == "Copied Subagent"
    assert subagent_copy["name"] == subagent["name"]
    assert main_agent_copy["capability_refs"] == main_agent["capability_refs"]
    assert main_agent_copy["subagents"] == main_agent["subagents"]
    assert subagent_copy["settings"] == subagent["settings"]
    assert client.get(f"/api/main-agents/{main_agent['id']}").json() == main_agent
    assert client.get(f"/api/subagents/{subagent['id']}").json() == subagent


def test_component_bulk_delete_detaches_optional_references(
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
    main_agent = client.post(
        "/api/main-agents",
        json={
            "name": "Bulk owner",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
        },
    ).json()
    ids = [required["filesystem"]["id"], second["id"]]

    deleted = client.post("/api/blocks/filesystem/delete", json={"ids": ids})
    assert deleted.json() == {"deleted": 2}
    assert all(
        client.get(f"/api/blocks/filesystem/{item_id}").status_code == 404
        for item_id in ids
    )
    stored = client.get(f"/api/main-agents/{main_agent['id']}").json()
    assert all(item["type"] != "filesystem" for item in stored["capability_refs"])

    assert client.delete(f"/api/main-agents/{main_agent['id']}").status_code == 200
    assert client.get("/api/blocks/filesystem").json() == []


def test_agent_configuration_bulk_delete_uses_one_command_per_category(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "bulk-agents", ("model", "filesystem", "output-mode")
    )
    main_agent_ids = []
    subagent_ids = []
    for index in range(2):
        main_agent_ids.append(client.post(
            "/api/main-agents",
            json={
                "name": f"Bulk Main Agent {index}",
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
        "/api/main-agents/delete", json={"ids": main_agent_ids}
    ).json() == {"deleted": 2}
    assert client.post(
        "/api/subagents/delete", json={"ids": subagent_ids}
    ).json() == {"deleted": 2}
    assert client.get("/api/main-agents").json() == []
    assert client.get("/api/subagents").json() == []


def test_agent_config_copy_rejects_duplicate_names_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "duplicate-copy", ("model", "filesystem", "output-mode")
    )
    main_agent = client.post(
        "/api/main-agents",
        json={
            "name": "Duplicate Main Agent",
            "capability_refs": references(
                required, ("model", "filesystem", "output-mode")
            ),
        },
    ).json()
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload("Duplicate Subagent", name="duplicate_worker"),
    ).json()

    main_agent_copy = client.post(
        f"/api/main-agents/{main_agent['id']}/copy",
        json={"name": main_agent["name"], "public_id": main_agent["public_id"]},
    )
    subagent_copy = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": subagent["component_name"]},
    )

    assert main_agent_copy.status_code == 409
    assert subagent_copy.status_code == 409
    assert client.get("/api/main-agents").json() == [main_agent]
    assert client.get("/api/subagents").json() == [subagent]


def test_agent_config_copy_returns_not_found_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    main_agent_copy = client.post(
        "/api/main-agents/missing/copy", json={"name": "Missing Main Agent copy"}
    )
    subagent_copy = client.post(
        "/api/subagents/missing/copy",
        json={"component_name": "Missing Subagent copy"},
    )

    assert main_agent_copy.status_code == 404
    assert subagent_copy.status_code == 404
    assert client.get("/api/main-agents").json() == []
    assert client.get("/api/subagents").json() == []


def test_agent_config_copy_revalidates_invalid_stored_sources_before_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client, "invalid-copy", ("model", "filesystem", "output-mode")
    )
    main_agent = client.post(
        "/api/main-agents",
        json={
            "name": "Invalid stored Main Agent",
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
        main_agent_payload = json.loads(
            connection.execute(
                "SELECT payload FROM main_agents WHERE id = ?", (main_agent["id"],)
            ).fetchone()[0]
        )
        main_agent_payload["capability_refs"][0]["block_id"] = "missing-block"
        subagent_payload_json = json.loads(
            connection.execute(
                "SELECT payload FROM subagents WHERE id = ?", (subagent["id"],)
            ).fetchone()[0]
        )
        subagent_payload_json["settings"]["capability_overrides"] = [
            {"type": "model", "mode": "replace", "block_id": "missing-block"}
        ]
        connection.execute(
            "UPDATE main_agents SET payload = ? WHERE id = ?",
            (json.dumps(main_agent_payload), main_agent["id"]),
        )
        connection.execute(
            "UPDATE subagents SET payload = ? WHERE id = ?",
            (json.dumps(subagent_payload_json), subagent["id"]),
        )

    before_main_agent = client.get(f"/api/main-agents/{main_agent['id']}").json()
    before_subagent = client.get(f"/api/subagents/{subagent['id']}").json()
    main_agent_copy = client.post(
        f"/api/main-agents/{main_agent['id']}/copy",
        json={"name": "Rejected Main Agent copy"},
    )
    subagent_copy = client.post(
        f"/api/subagents/{subagent['id']}/copy",
        json={"component_name": "Rejected Subagent copy"},
    )

    assert main_agent_copy.status_code == 422
    assert subagent_copy.status_code == 422
    assert client.get(f"/api/main-agents/{main_agent['id']}").json() == before_main_agent
    assert client.get(f"/api/subagents/{subagent['id']}").json() == before_subagent
    assert len(client.get("/api/main-agents").json()) == 1
    assert len(client.get("/api/subagents").json()) == 1
