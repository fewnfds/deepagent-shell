from __future__ import annotations

from contextlib import closing
import json
import sqlite3

import pytest

from agent_shell.provider_secrets import ProviderCredentialError, ProviderSecretResolver
from agent_shell.storage.database import SQLiteDatabase

from .provider_secret_support import *

def test_local_secret_is_write_only_and_separated_from_block_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)

    created = client.post("/api/blocks/model", json=model_payload())
    assert created.status_code == 200, created.text
    block = created.json()
    block_id = block["id"]
    responses = [
        created,
        client.get("/api/blocks/model"),
        client.get(f"/api/blocks/model/{block_id}"),
    ]

    assert block["credential"] == {"status": "masked"}
    assert all(LOCAL_SECRET not in response.text for response in responses)
    assert all("reference" not in response.text for response in responses)
    stored, secrets = database_payload(database_path, block_id)
    assert LOCAL_SECRET not in json.dumps(stored)
    assert stored["credential"]["reference"] == secrets[0]["id"]
    assert secrets[0]["secret_value"] == LOCAL_SECRET

    resolver = ProviderSecretResolver(SQLiteDatabase(database_path))
    assert resolver.resolve_model(block_id) == LOCAL_SECRET

def test_keep_rename_replace_and_masked_round_trip_are_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    block_id = block["id"]
    original_payload, _ = database_payload(database_path, block_id)
    original_reference = original_payload["credential"]["reference"]

    kept_payload = model_payload("Renamed model", None)
    kept = client.put(f"/api/blocks/model/{block_id}", json=kept_payload)
    assert kept.status_code == 200, kept.text
    kept_internal, kept_secrets = database_payload(database_path, block_id)
    assert kept.json()["id"] == block_id
    assert kept.json()["name"] == "Renamed model"
    assert kept_internal["credential"]["reference"] == original_reference
    assert [row["secret_value"] for row in kept_secrets] == [LOCAL_SECRET]

    masked = model_payload(
        "Masked overwrite",
        "••••••••",
    )
    rejected = client.put(f"/api/blocks/model/{block_id}", json=masked)
    assert rejected.status_code == 422
    assert ProviderSecretResolver(SQLiteDatabase(database_path)).resolve_model(
        block_id
    ) == LOCAL_SECRET

    replacement = model_payload("Rotated model", REPLACEMENT_SECRET)
    rotated = client.put(f"/api/blocks/model/{block_id}", json=replacement)
    assert rotated.status_code == 200, rotated.text
    rotated_internal, rotated_secrets = database_payload(database_path, block_id)
    assert rotated_internal["credential"]["reference"] != original_reference
    assert [row["secret_value"] for row in rotated_secrets] == [REPLACEMENT_SECRET]
    assert ProviderSecretResolver(SQLiteDatabase(database_path)).resolve_model(
        block_id
    ) == REPLACEMENT_SECRET

def test_endpoint_change_without_replacement_clears_saved_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    changed = model_payload("Changed endpoint", None)
    changed["base_url"] = "https://other-provider.example/v1"

    response = client.put(f"/api/blocks/model/{block['id']}", json=changed)

    assert response.status_code == 200, response.text
    assert response.json()["credential"] == {"status": "missing"}
    stored, secrets = database_payload(database_path, block["id"])
    assert stored["base_url"] == "https://other-provider.example/v1"
    assert stored["credential"] is None
    assert secrets == []
    assert ProviderSecretResolver(SQLiteDatabase(database_path)).resolve_model(
        block["id"]
    ) is None

def test_provider_change_without_replacement_clears_saved_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    changed = model_payload("Changed Provider", None)
    changed["provider"] = "anthropic"
    changed["provider_settings"] = {"max_tokens_to_sample": 1024}

    response = client.put(f"/api/blocks/model/{block['id']}", json=changed)

    assert response.status_code == 200, response.text
    assert response.json()["credential"] == {"status": "missing"}
    stored, secrets = database_payload(database_path, block["id"])
    assert stored["provider"] == "anthropic"
    assert stored["credential"] is None
    assert secrets == []

def test_copy_reuses_opaque_reference_and_last_owner_delete_removes_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    source = client.post("/api/blocks/model", json=model_payload()).json()

    copied = client.post(
        f"/api/blocks/model/{source['id']}/copy", json={"name": "Copied model"}
    )
    assert copied.status_code == 200, copied.text
    copy_id = copied.json()["id"]
    source_internal, secrets = database_payload(database_path, source["id"])
    copy_internal, _ = database_payload(database_path, copy_id)
    assert source_internal["credential"]["reference"] == (
        copy_internal["credential"]["reference"]
    )
    assert len(secrets) == 1
    assert LOCAL_SECRET not in copied.text

    assert client.delete(f"/api/blocks/model/{source['id']}").status_code == 200
    assert ProviderSecretResolver(SQLiteDatabase(database_path)).resolve_model(
        copy_id
    ) == LOCAL_SECRET
    assert client.delete(f"/api/blocks/model/{copy_id}").status_code == 200
    with closing(sqlite3.connect(database_path)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM provider_secrets").fetchone()[0] == 0

def test_no_key_is_valid_but_a_broken_reference_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    resolver = ProviderSecretResolver(SQLiteDatabase(database_path))
    monkeypatch.setenv("TEST_PROVIDER_KEY", "must-not-be-read")
    no_key = client.post(
        "/api/blocks/model", json=model_payload("No-key model", None)
    )
    assert no_key.status_code == 200, no_key.text
    assert no_key.json()["credential"] == {"status": "missing"}
    assert resolver.resolve_model(no_key.json()["id"]) is None

    block = client.post("/api/blocks/model", json=model_payload()).json()
    internal, _ = database_payload(database_path, block["id"])
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "DELETE FROM provider_secrets WHERE id = ?",
            (internal["credential"]["reference"],),
        )
        connection.commit()
    with pytest.raises(ProviderCredentialError) as captured:
        resolver.resolve_model(block["id"])
    assert captured.value.code == "provider_secret_reference_missing"
    assert client.get(f"/api/blocks/model/{block['id']}").json()["credential"][
        "status"
    ] == "missing"
