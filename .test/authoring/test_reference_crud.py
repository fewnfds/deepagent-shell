from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from .reference_support import *


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


def test_subagent_override_self_reference_and_external_delete_protection(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    target = client.post(
        "/api/subagent-overrides",
        json={"name": "Recursive target", "capability_overrides": []},
    ).json()
    self_binding = {
        "name": "recursive_worker",
        "description": "Continues the same recursive role.",
        "subagent_override_id": target["id"],
    }
    recursive = client.put(
        f"/api/subagent-overrides/{target['id']}",
        json={
            "name": target["name"],
            "capability_overrides": [],
            "subagents": [self_binding],
        },
    )
    assert recursive.status_code == 200, recursive.text
    assert recursive.json()["subagents"] == [self_binding]

    external = client.post(
        "/api/subagent-overrides",
        json={
            "name": "External owner",
            "capability_overrides": [],
            "subagents": [{
                **self_binding,
                "name": "target_worker",
            }],
        },
    )
    assert external.status_code == 200, external.text

    blocked = client.delete(f"/api/subagent-overrides/{target['id']}")
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == {
        "code": "configuration_referenced",
        "message": "The configuration is still referenced by a Subagent override.",
        "message_key": "errors.configurationReferencedBySubagentOverride",
        "message_args": {"owner": "External owner"},
    }

    released = client.post(
        "/api/subagent-overrides/delete",
        json={"ids": [target["id"], external.json()["id"]]},
    )
    assert released.status_code == 200, released.text
    assert released.json() == {"deleted": 2}


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
        "include_client_messages",
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
