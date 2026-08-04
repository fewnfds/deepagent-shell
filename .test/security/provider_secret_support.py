from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_shell.app import create_app
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


__all__ = [
    "LOCAL_SECRET",
    "REPLACEMENT_SECRET",
    "clean_agent_shell_environment",
    "database_payload",
    "make_client",
    "model_payload",
]
