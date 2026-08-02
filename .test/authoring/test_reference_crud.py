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

def test_primary_reference_create_update_and_delete_protection_cover_every_type(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    original = create_blocks(client, "original")
    replacement = create_blocks(client, "replacement")

    response = client.post(
        "/api/primary-agents",
        json={
            "name": "Primary matrix",
            "capability_refs": references(original),
            "subagents": [{
                "name": "matrix_worker",
                "description": "Exercises every selected capability reference.",
                "subagent_override_id": "",
            }],
        },
    )
    assert response.status_code == 200, response.text
    primary = response.json()
    assert [item["type"] for item in primary["capability_refs"]] == list(PUBLIC_TYPES)

    for capability_type, block in original.items():
        blocked = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert blocked.status_code == 409, (capability_type, blocked.text)

    updated = client.put(
        f"/api/primary-agents/{primary['id']}",
        json={
            "name": primary["name"],
            "capability_refs": references(replacement),
            "subagents": primary["subagents"],
        },
    )
    assert updated.status_code == 200, updated.text

    for capability_type, block in original.items():
        released = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert released.status_code == 200, (capability_type, released.text)
    for capability_type, block in replacement.items():
        blocked = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert blocked.status_code == 409, (capability_type, blocked.text)

    assert client.delete(f"/api/primary-agents/{primary['id']}").status_code == 200
    for capability_type, block in replacement.items():
        released = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert released.status_code == 200, (capability_type, released.text)

def test_override_replace_update_modes_and_delete_protection_cover_every_type(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    original = create_blocks(client, "override-original", OVERRIDEABLE_TYPES)

    response = client.post(
        "/api/subagent-overrides",
        json={
            "name": "Override matrix",
            "capability_overrides": [
                {
                    "type": capability_type,
                    "mode": "replace",
                    "block_id": original[capability_type]["id"],
                }
                for capability_type in OVERRIDEABLE_TYPES
            ],
        },
    )
    assert response.status_code == 200, response.text
    override = response.json()

    for capability_type, block in original.items():
        blocked = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert blocked.status_code == 409, (capability_type, blocked.text)

    passive_modes = [
        {
            "type": capability_type,
            "mode": "disabled",
            "block_id": "",
        }
        for index, capability_type in enumerate(OVERRIDEABLE_TYPES)
        if index % 2 == 1
    ]
    updated = client.put(
        f"/api/subagent-overrides/{override['id']}",
        json={"name": override["name"], "capability_overrides": passive_modes},
    )
    assert updated.status_code == 200, updated.text
    assert [item["mode"] for item in updated.json()["capability_overrides"]] == [
        item["mode"] for item in passive_modes
    ]

    for capability_type, block in original.items():
        released = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert released.status_code == 200, (capability_type, released.text)
    assert client.delete(f"/api/subagent-overrides/{override['id']}").status_code == 200

def test_binding_delete_protection_only_tracks_override_references(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required_refs = references(
        create_blocks(client, "binding-required", ("model", "filesystem", "output-mode")),
        ("model", "filesystem", "output-mode"),
    )
    override_response = client.post(
        "/api/subagent-overrides",
        json={"name": "Shared override", "capability_overrides": []},
    )
    assert override_response.status_code == 200, override_response.text
    override = override_response.json()

    owner_response = client.post(
        "/api/primary-agents",
        json={
            "name": "Override owner",
            "capability_refs": required_refs,
            "subagents": [
                {
                    "name": "draft_worker",
                    "description": "Bindings own saved override references.",
                    "subagent_override_id": override["id"],
                }
            ],
        },
    )
    assert owner_response.status_code == 200, owner_response.text
    owner = owner_response.json()

    independent_response = client.post(
        "/api/primary-agents",
        json={"name": "Independent Primary", "capability_refs": required_refs},
    )
    assert independent_response.status_code == 200, independent_response.text
    independent = independent_response.json()
    assert client.delete(f"/api/primary-agents/{independent['id']}").status_code == 200

    override_blocked = client.delete(f"/api/subagent-overrides/{override['id']}")
    assert override_blocked.status_code == 409, override_blocked.text
    assert override_blocked.json()["detail"] == {
        "code": "configuration_referenced",
        "message": "The configuration is still referenced by a Primary Agent.",
        "message_key": "errors.configurationReferencedByPrimary",
        "message_args": {"owner": "Override owner"},
    }

    assert client.delete(f"/api/primary-agents/{owner['id']}").status_code == 200
    assert client.delete(f"/api/subagent-overrides/{override['id']}").status_code == 200

def test_binding_uses_current_primary_and_optional_override_only(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required_refs = references(
        create_blocks(client, "binding-flags-required", ("model", "filesystem", "output-mode")),
        ("model", "filesystem", "output-mode"),
    )
    valid = client.post(
        "/api/primary-agents",
        json={
            "name": "Unsaved self Primary",
            "capability_refs": required_refs,
            "subagents": [
                {
                    "name": "self_worker",
                    "description": "Inherits the current Primary without an override.",
                    "subagent_override_id": "",
                }
            ],
        },
    )
    assert valid.status_code == 200, valid.text
    primary = valid.json()
    assert set(primary["subagents"][0]) == {
        "name",
        "description",
        "subagent_override_id",
    }

    override = client.post(
        "/api/subagent-overrides",
        json={"name": "Optional override", "capability_overrides": []},
    )
    assert override.status_code == 200, override.text
    updated_payload = {
        "name": primary["name"],
        "capability_refs": required_refs,
        "subagents": [
            {
                "name": "self_worker",
                "description": "Applies an optional override to the current Primary.",
                "subagent_override_id": override.json()["id"],
            }
        ],
    }
    updated = client.put(f"/api/primary-agents/{primary['id']}", json=updated_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["subagents"][0]["subagent_override_id"] == override.json()["id"]

    for removed_field in (
        "enabled",
        "use_current_primary",
        "primary_agent_id",
        "inherit_all",
    ):
        response = client.post(
            "/api/primary-agents",
            json={
                "name": f"Removed binding field {removed_field}",
                "capability_refs": required_refs,
                "subagents": [
                    {
                        "name": "worker",
                        "description": "Removed source fields are not accepted.",
                        "subagent_override_id": "",
                        removed_field: True,
                    }
                ],
            },
        )
        assert response.status_code == 422, response.text

def test_reference_contracts_reject_unknown_duplicate_wrong_type_and_force_removed(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(client, "validation", ("model", "filesystem", "output-mode"))
    model = required["model"]
    required_refs = references(required, ("model", "filesystem", "output-mode"))

    invalid_primary_refs = [
        [
            *required_refs,
            {"type": "unknown-capability", "block_id": model["id"]},
        ],
        [
            {"type": "model", "block_id": model["id"]},
            {"type": "model", "block_id": model["id"]},
            required_refs[1],
            required_refs[2],
        ],
        [
            required_refs[0],
            {"type": "filesystem", "block_id": model["id"]},
            required_refs[2],
        ],
    ]
    for index, capability_refs in enumerate(invalid_primary_refs):
        response = client.post(
            "/api/primary-agents",
            json={"name": f"Invalid Primary {index}", "capability_refs": capability_refs},
        )
        assert response.status_code == 422, response.text

    invalid_overrides = [
        [{"type": "unknown-capability", "mode": "inherit", "block_id": ""}],
        [{"type": "subagent", "mode": "disabled", "block_id": ""}],
        [{"type": "prompt-preset", "mode": "disabled", "block_id": ""}],
        [{"type": "filesystem", "mode": "disabled", "block_id": ""}],
        [{"type": "model", "mode": "unsupported", "block_id": ""}],
        [{"type": "model", "mode": "replace", "block_id": ""}],
        [{"type": "model", "mode": "disabled", "block_id": ""}],
        [
            {"type": "model", "mode": "inherit", "block_id": ""},
            {"type": "model", "mode": "disabled", "block_id": ""},
        ],
    ]
    for index, capability_overrides in enumerate(invalid_overrides):
        response = client.post(
            "/api/subagent-overrides",
            json={
                "name": f"Invalid Override {index}",
                "capability_overrides": capability_overrides,
            },
        )
        assert response.status_code == 422, response.text

def test_primary_save_enforces_required_and_delegation_contracts_with_skill_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    blocks = create_blocks(
        client,
        "save-contract",
        ("model", "output-mode", "filesystem", "skill", "subagent"),
    )
    required_refs = references(blocks, ("model", "output-mode"))

    missing_required = [
        [],
        [required_refs[1]],
        [required_refs[0]],
    ]
    for index, capability_refs in enumerate(missing_required):
        response = client.post(
            "/api/primary-agents",
            json={
                "name": f"Missing required {index}",
                "capability_refs": capability_refs,
            },
        )
        assert response.status_code == 422, response.text

    without_filesystem = client.post(
        "/api/primary-agents",
        json={
            "name": "No filesystem required",
            "capability_refs": required_refs,
        },
    )
    assert without_filesystem.status_code == 200, without_filesystem.text

    skill_without_filesystem = client.post(
        "/api/primary-agents",
        json={
            "name": "Skill without filesystem",
            "capability_refs": [
                *required_refs,
                {"type": "skill", "block_id": blocks["skill"]["id"]},
            ],
        },
    )
    assert skill_without_filesystem.status_code == 200, skill_without_filesystem.text

    delegation = client.post(
        "/api/blocks/subagent",
        json={"name": "Delegation"},
    ).json()
    delegation_without_binding = client.post(
        "/api/primary-agents",
        json={
            "name": "Delegation without binding",
            "capability_refs": [
                *required_refs,
                {"type": "subagent", "block_id": delegation["id"]},
            ],
        },
    )
    assert delegation_without_binding.status_code == 422
    issues = delegation_without_binding.json()["detail"]["validation"]["issues"]
    assert any(
        issue["code"] == "assembly.subagent_binding_required" for issue in issues
    )

    child_skill_override = client.post(
        "/api/subagent-overrides",
        json={
            "name": "Child skill without filesystem",
            "capability_overrides": [
                {
                    "type": "skill",
                    "mode": "replace",
                    "block_id": blocks["skill"]["id"],
                }
            ],
        },
    )
    assert child_skill_override.status_code == 200, child_skill_override.text
    child_skill_without_filesystem = client.post(
        "/api/primary-agents",
        json={
            "name": "Child Skill fallback",
            "capability_refs": [
                *required_refs,
                {"type": "subagent", "block_id": delegation["id"]},
            ],
            "subagents": [
                {
                    "name": "skill_worker",
                    "description": "Selects a Skill without a filesystem.",
                    "subagent_override_id": child_skill_override.json()["id"],
                }
            ],
        },
    )
    assert child_skill_without_filesystem.status_code == 200, (
        child_skill_without_filesystem.text
    )

    valid = client.post(
        "/api/primary-agents",
        json={
            "name": "Complete required contract",
            "capability_refs": [
                *required_refs,
                {
                    "type": "filesystem",
                    "block_id": blocks["filesystem"]["id"],
                },
                {"type": "skill", "block_id": blocks["skill"]["id"]},
                {"type": "subagent", "block_id": delegation["id"]},
            ],
            "subagents": [
                {
                    "name": "self_worker",
                    "description": "Uses the complete Primary configuration.",
                    "subagent_override_id": "",
                }
            ],
        },
    )
    assert valid.status_code == 200, valid.text
