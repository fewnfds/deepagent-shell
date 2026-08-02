from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_shell.app import create_app
from agent_shell.settings import get_settings
from agent_shell.storage.permissions import PermissionStatus
from support import API_KEY, ScopedAuthTestClient, configure_scope_tokens


@pytest.fixture(autouse=True)
def clean_agent_shell_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("AGENT_SHELL_"):
            monkeypatch.delenv(key, raising=False)


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    configure_scope_tokens(monkeypatch, tmp_path)
    app = create_app()
    return app, ScopedAuthTestClient(app)


def _payload(**overrides) -> dict:
    payload = {
        "host": "127.0.0.1",
        "port": 19100,
        "allow_remote": False,
        "management_token": {"operation": "preserve"},
        "cors_origins": [],
        "trusted_proxy_cidrs": [],
    }
    payload.update(overrides)
    return payload


def test_system_settings_get_reports_secret_status_without_secret_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client = _client(tmp_path, monkeypatch)
    management = os.environ["AGENT_SHELL_MANAGEMENT_TOKEN"]

    response = client.get("/api/system/settings")

    assert response.status_code == 200
    assert response.json() == {
        "host": "127.0.0.1",
        "port": 19100,
        "allow_remote": False,
        "cors_origins": [],
        "trusted_proxy_cidrs": [],
        "management_token": {"configured": True},
        "restart_required": False,
        "active_management_url": "http://testserver/admin",
    }
    assert management not in response.text


def test_valid_system_settings_are_atomic_and_take_effect_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client = _client(tmp_path, monkeypatch)
    settings_path = tmp_path / "data" / "config" / "agent-shell.env"
    settings_path.write_text("# launcher comment\n", encoding="utf-8")

    response = client.put(
        "/api/system/settings",
        json=_payload(
            port=9123,
            cors_origins=["https://CONSOLE.example:8443"],
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["restart_required"] is True
    assert response.json()["port"] == 9123
    assert response.json()["cors_origins"] == ["https://console.example:8443"]
    assert app.state.settings.port == 19100
    text = settings_path.read_text(encoding="utf-8")
    assert "# launcher comment" in text
    assert "AGENT_SHELL_PORT=9123" in text
    restarted = get_settings(
        application_home=tmp_path,
        include_process_environment=False,
    )
    assert restarted.port == 9123
    assert restarted.cors_origins == ("https://console.example:8443",)


def test_invalid_candidate_does_not_write_or_reveal_replacement_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client = _client(tmp_path, monkeypatch)
    replacement = "replacement-management-secret-000000"
    settings_path = tmp_path / "data" / "config" / "agent-shell.env"

    response = client.put(
        "/api/system/settings",
        json=_payload(
            host="0.0.0.0",
            management_token={"operation": "replace", "value": replacement},
        ),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "system_settings_invalid"
    assert replacement not in response.text
    assert not settings_path.exists()


def test_management_password_replacement_is_write_only_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client = _client(tmp_path, monkeypatch)
    old_management = os.environ["AGENT_SHELL_MANAGEMENT_TOKEN"]
    replacement = "new-management-password"

    response = client.put(
        "/api/system/settings",
        json=_payload(
            management_token={"operation": "replace", "value": replacement},
        ),
    )

    assert response.status_code == 200
    assert replacement not in response.text
    assert old_management not in response.text
    restarted = get_settings(
        application_home=tmp_path,
        include_process_environment=False,
    )
    assert restarted.management_token is not None
    assert restarted.management_token.get_secret_value() == replacement


def test_management_password_can_equal_the_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client = _client(tmp_path, monkeypatch)

    response = client.put(
        "/api/system/settings",
        json=_payload(
            management_token={"operation": "replace", "value": API_KEY},
        ),
    )

    assert response.status_code == 200
    restarted = get_settings(
        application_home=tmp_path,
        include_process_environment=False,
    )
    assert restarted.management_token is not None
    assert restarted.management_token.get_secret_value() == API_KEY


def test_permission_failure_leaves_existing_settings_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client = _client(tmp_path, monkeypatch)
    settings_path = tmp_path / "data" / "config" / "agent-shell.env"
    original = "# existing launcher comment\n"
    settings_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        "agent_shell.system_settings.secure_file",
        lambda _path: PermissionStatus(
            "file",
            False,
            "test-unconfirmed",
            "The test did not confirm private permissions.",
        ),
    )

    response = client.put(
        "/api/system/settings",
        json=_payload(port=9124),
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "system_settings_write_failed"
    assert settings_path.read_text(encoding="utf-8") == original
