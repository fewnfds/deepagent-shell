from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_shell import __version__
from agent_shell.app import create_app
from agent_shell.provider_secrets import ProviderCredentialError, ProviderSecretResolver
from agent_shell.storage.database import SQLiteDatabase
from support import ScopedAuthTestClient, configure_scope_tokens


LOCAL_SECRET = "local-provider-secret-sentinel"
REPLACEMENT_SECRET = "replacement-provider-secret-sentinel"


@pytest.fixture(autouse=True)
def clean_agent_shell_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("AGENT_SHELL_") or key == "TEST_PROVIDER_KEY":
            monkeypatch.delenv(key, raising=False)


def make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Path]:
    monkeypatch.chdir(tmp_path)
    configure_scope_tokens(monkeypatch, tmp_path)
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    return ScopedAuthTestClient(create_app()), database_path


def model_payload(
    name: str = "Secret model",
    credential: str | None = LOCAL_SECRET,
) -> dict:
    return {
        "name": name,
        "provider": "openai",
        "base_url": "https://provider.example/v1",
        "credential": credential,
        "model": "provider-model",
        "provider_settings": {
            "temperature": 0.7,
            "max_completion_tokens": 4096,
        },
        "tool_choice": None,
        "response_format": None,
        "model_settings": {},
    }


def database_payload(database_path: Path, block_id: str) -> tuple[dict, list[sqlite3.Row]]:
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM blocks WHERE id = ?", (block_id,)
            ).fetchone()["payload"]
        )
        secrets = connection.execute(
            "SELECT id, secret_value FROM provider_secrets ORDER BY id"
        ).fetchall()
    return payload, secrets


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


def test_invalid_historical_credential_metadata_stays_readable_and_repairable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM blocks WHERE id = ?", (block["id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["credential"] = {"legacy_path": r"C:\private\provider-secret.txt"}
        connection.execute(
            "UPDATE blocks SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), block["id"]),
        )

    loaded = client.get(f"/api/blocks/model/{block['id']}")
    listed = client.get("/api/blocks/model")
    report = client.get("/api/validation/repository")

    assert loaded.status_code == 200
    assert listed.status_code == 200
    assert loaded.json()["credential"] == {"status": "missing"}
    assert r"C:\private" not in loaded.text
    issue = next(
        item
        for item in report.json()["issues"]
        if item["code"] == "storage.credential_metadata_invalid"
    )
    assert issue["owner_id"] == block["id"]
    assert r"C:\private" not in report.text

    repaired = client.put(
        f"/api/blocks/model/{block['id']}",
        json=model_payload("Repaired model", REPLACEMENT_SECRET),
    )
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["credential"] == {"status": "masked"}
    assert ProviderSecretResolver(SQLiteDatabase(database_path)).resolve_model(
        block["id"]
    ) == REPLACEMENT_SECRET


def test_old_command_shapes_environment_source_and_plain_api_key_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)

    command_shape = client.post(
        "/api/blocks/model",
        json=model_payload(credential={"operation": "keep"}),  # type: ignore[arg-type]
    )
    environment_shape = client.post(
        "/api/blocks/model",
        json=model_payload(  # type: ignore[arg-type]
            "Environment shape",
            {"operation": "replace", "source": "environment", "name": "TEST_PROVIDER_KEY"},
        ),
    )
    plain = model_payload()
    plain.pop("credential")
    plain["api_key"] = LOCAL_SECRET
    plaintext_field = client.post("/api/blocks/model", json=plain)
    missing_credential = model_payload("Missing credential")
    missing_credential.pop("credential")
    invalid_catalog_credential = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": "https://provider.example/v1",
            "credential": {"operation": "keep"},
            "block_id": "",
        },
    )

    assert command_shape.status_code == 422
    assert environment_shape.status_code == 422
    assert plaintext_field.status_code == 422
    assert client.post("/api/blocks/model", json=missing_credential).status_code == 422
    assert invalid_catalog_credential.status_code == 422
    assert LOCAL_SECRET not in plaintext_field.text


def test_model_catalog_uses_entered_or_saved_key_and_allows_no_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    observed: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(
            (
                request.headers.get("Authorization", ""),
                request.headers.get("User-Agent", ""),
            )
        )
        return httpx.Response(
            200,
            request=request,
            json={"data": [{"id": "one", "owned_by": "provider-private"}]},
        )

    monkeypatch.setattr(
        "agent_shell.provider_http.ProviderAsyncCurlTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    response = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": block["base_url"],
            "credential": None,
            "block_id": block["id"],
        },
    )
    no_key_response = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": block["base_url"],
            "credential": None,
            "block_id": "",
        },
    )

    assert response.status_code == 200
    assert no_key_response.status_code == 200
    assert response.json() == ["one"]
    assert observed == [
        (f"Bearer {LOCAL_SECRET}", f"Agent-Shell/{__version__}"),
        ("", f"Agent-Shell/{__version__}"),
    ]
    assert LOCAL_SECRET not in response.text
    assert "provider-private" not in response.text


def test_model_catalog_never_reuses_saved_key_for_a_different_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    upstream_called = False

    def unexpected_client(**kwargs):
        nonlocal upstream_called
        upstream_called = True
        raise AssertionError("the changed endpoint must not receive an upstream request")

    monkeypatch.setattr(
        "agent_shell.provider_http.ProviderAsyncCurlTransport", unexpected_client
    )
    response = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": "https://other-provider.example/v1",
            "credential": None,
            "block_id": block["id"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "provider_credential_connection_changed"
    assert upstream_called is False
    assert LOCAL_SECRET not in response.text


def test_model_catalog_reports_cloudflare_browser_challenge_without_leaking_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            headers={"Cf-Mitigated": "challenge", "Server": "cloudflare"},
            text="provider-private challenge body",
        )

    monkeypatch.setattr(
        "agent_shell.provider_http.ProviderAsyncCurlTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    response = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": "https://provider.example/v1",
            "credential": LOCAL_SECRET,
            "block_id": "",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "model_catalog_browser_challenge"
    assert "provider-private" not in response.text


def test_model_catalog_never_reuses_saved_key_for_a_different_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    block = client.post("/api/blocks/model", json=model_payload()).json()
    upstream_called = False

    def unexpected_client(**kwargs):
        nonlocal upstream_called
        upstream_called = True
        raise AssertionError("the changed Provider must not receive an upstream request")

    monkeypatch.setattr(
        "agent_shell.provider_http.ProviderAsyncCurlTransport", unexpected_client
    )
    response = client.post(
        "/api/fetch-models",
        json={
            "provider": "deepseek",
            "base_url": block["base_url"],
            "credential": None,
            "block_id": block["id"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "provider_credential_connection_changed"
    assert upstream_called is False
    assert LOCAL_SECRET not in response.text


@pytest.mark.parametrize(
    "provider_payload",
    [
        {"unexpected": []},
        {"data": "not-a-list"},
        {"data": [{"id": ""}]},
        {"data": [{"id": 123}]},
        {"data": [{"id": "safe-model", "secret_field": "provider-private"}, None]},
    ],
)
def test_model_catalog_rejects_malformed_provider_payload_without_leaking_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_payload: object,
) -> None:
    client, _ = make_client(tmp_path, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=provider_payload)

    monkeypatch.setattr(
        "agent_shell.provider_http.ProviderAsyncCurlTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    response = client.post(
        "/api/fetch-models",
        json={
            "provider": "openai",
            "base_url": "https://provider.example/v1",
            "credential": None,
            "block_id": "",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_model_catalog_response"
    assert "provider-private" not in response.text
