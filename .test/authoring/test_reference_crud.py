from __future__ import annotations

import json
import sqlite3
from uuid import UUID

from .reference_support import *

def test_primary_reference_delete_detaches_optional_and_protects_required_types(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    original = create_blocks(client, "original")
    replacement = create_blocks(client, "replacement")
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Matrix worker",
            name="matrix_worker",
            description="Exercises every selected capability reference.",
        ),
    ).json()

    response = client.post(
        "/api/primary-agents",
        json={
            "name": "Primary matrix",
            "capability_refs": references(original),
            "subagents": [{"subagent_id": subagent["id"]}],
        },
    )
    assert response.status_code == 200, response.text
    primary = response.json()
    assert [item["type"] for item in primary["capability_refs"]] == list(PUBLIC_TYPES)

    for capability_type, block in original.items():
        deleted = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        expected = 409 if capability_type in REQUIRED_TYPES else 200
        assert deleted.status_code == expected, (capability_type, deleted.text)

    updated = client.put(
        f"/api/primary-agents/{primary['id']}",
        json={
            "name": primary["name"],
            "capability_refs": references(replacement),
            "subagents": primary["subagents"],
        },
    )
    assert updated.status_code == 200, updated.text

    for capability_type in REQUIRED_TYPES:
        block = original[capability_type]
        released = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert released.status_code == 200, (capability_type, released.text)
    for capability_type, block in replacement.items():
        deleted = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        expected = 409 if capability_type in REQUIRED_TYPES else 200
        assert deleted.status_code == expected, (capability_type, deleted.text)

    assert client.delete(f"/api/primary-agents/{primary['id']}").status_code == 200
    for capability_type in REQUIRED_TYPES:
        block = replacement[capability_type]
        released = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert released.status_code == 200, (capability_type, released.text)

def test_subagent_replace_references_are_detached_when_blocks_are_deleted(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    original = create_blocks(client, "override-original", OVERRIDEABLE_TYPES)

    response = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Override matrix",
            name="override_matrix",
            capability_overrides=[
                {
                    "type": capability_type,
                    "mode": "replace",
                    "block_id": original[capability_type]["id"],
                }
                for capability_type in OVERRIDEABLE_TYPES
            ],
        ),
    )
    assert response.status_code == 200, response.text
    subagent = response.json()

    for capability_type, block in original.items():
        deleted = client.delete(f"/api/blocks/{capability_type}/{block['id']}")
        assert deleted.status_code == 200, (capability_type, deleted.text)
    stored = client.get(f"/api/subagents/{subagent['id']}").json()
    assert stored["settings"]["capability_overrides"] == []

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
        f"/api/subagents/{subagent['id']}",
        json=subagent_payload(
            subagent["component_name"],
            name=subagent["name"],
            description=subagent["description"],
            capability_overrides=passive_modes,
        ),
    )
    assert updated.status_code == 200, updated.text
    assert [
        item["mode"]
        for item in updated.json()["settings"]["capability_overrides"]
    ] == [
        item["mode"] for item in passive_modes
    ]

    assert client.delete(f"/api/subagents/{subagent['id']}").status_code == 200

def test_subagent_delete_detaches_entity_references(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required_refs = references(
        create_blocks(client, "binding-required", ("model", "filesystem", "output-mode")),
        ("model", "filesystem", "output-mode"),
    )
    subagent_response = client.post(
        "/api/subagents",
        json=subagent_payload("Shared Subagent", name="draft_worker"),
    )
    assert subagent_response.status_code == 200, subagent_response.text
    subagent = subagent_response.json()

    owner_response = client.post(
        "/api/primary-agents",
        json={
            "name": "Override owner",
            "capability_refs": required_refs,
            "subagents": [{"subagent_id": subagent["id"]}],
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

    deleted = client.delete(f"/api/subagents/{subagent['id']}")
    assert deleted.status_code == 200, deleted.text
    stored_owner = client.get(f"/api/primary-agents/{owner['id']}").json()
    assert stored_owner["subagents"] == []

    assert client.delete(f"/api/primary-agents/{owner['id']}").status_code == 200

def test_subagent_delete_detaches_self_and_external_references(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    target = client.post(
        "/api/subagents",
        json=subagent_payload("Recursive target", name="recursive_worker"),
    ).json()
    self_reference = {"subagent_id": target["id"]}
    recursive = client.put(
        f"/api/subagents/{target['id']}",
        json=subagent_payload(
            target["component_name"],
            name=target["name"],
            description=target["description"],
            subagents=[self_reference],
        ),
    )
    assert recursive.status_code == 200, recursive.text
    assert recursive.json()["settings"]["subagents"] == [self_reference]

    external = client.post(
        "/api/subagents",
        json=subagent_payload(
            "External owner",
            name="external_owner",
            subagents=[self_reference],
        ),
    )
    assert external.status_code == 200, external.text

    deleted = client.delete(f"/api/subagents/{target['id']}")
    assert deleted.status_code == 200, deleted.text
    stored_external = client.get(
        f"/api/subagents/{external.json()['id']}"
    ).json()
    assert stored_external["settings"]["subagents"] == []

    released = client.post(
        "/api/subagents/delete",
        json={"ids": [external.json()["id"]]},
    )
    assert released.status_code == 200, released.text
    assert released.json() == {"deleted": 1}
