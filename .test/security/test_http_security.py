from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import re
import subprocess
import zipfile

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from agent_shell.app import create_app
from agent_shell.security import SecurityFailure, _parse_bearer
from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.database import SQLiteDatabase


MANAGEMENT_TOKEN = "management-test-secret-000000000000"
API_KEY = "api-test-secret-111111111111"


class _AdminAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []
        self.external: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        target = ""
        if tag == "script":
            target = attributes.get("src") or ""
        elif tag == "link" and "stylesheet" in (attributes.get("rel") or "").split():
            target = attributes.get("href") or ""
        if not target:
            return
        if target.startswith(("http://", "https://", "//")):
            self.external.append(target)
        else:
            self.assets.append(target)


@pytest.fixture(autouse=True)
def clean_agent_shell_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key.upper().startswith("AGENT_SHELL_"):
            monkeypatch.delenv(key, raising=False)


def _configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", MANAGEMENT_TOKEN)


def _configure_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_paths(monkeypatch, tmp_path)
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    ApiServerStore(database).update_settings(
        api_key_operation="replace",
        api_key=API_KEY,
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_static_shell_remain_public_when_api_auth_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        health = client.get("/api/health")
        admin = client.get("/admin")
        protected = client.get("/api/catalog")

    assert health.status_code == 200
    assert admin.status_code == 200
    assert protected.status_code == 401


def test_admin_shell_uses_only_bundled_script_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app(), follow_redirects=False) as client:
        root = client.get("/")
        admin = client.get("/admin")
        favicon = client.get("/admin/favicon.ico")
        parser = _AdminAssetParser()
        parser.feed(admin.text)
        assets = {path: client.get(path) for path in parser.assets}
        removed_assets = [
            client.get(path)
            for path in (
                "/admin/assets/vendor/vue-3.5.13.global.prod.js",
                "/admin/assets/icons.js",
                "/admin/assets/api.js",
            )
        ]
        protected = client.get("/api/catalog")
        authorized = client.get(
            "/api/catalog", headers=_bearer(MANAGEMENT_TOKEN)
        )

    assert root.status_code == 307
    assert root.headers["location"] == "/admin"
    assert admin.status_code == 200
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/x-icon")
    assert favicon.content
    assert parser.external == []
    assert parser.assets
    assert len(parser.assets) == len(set(parser.assets))
    for path, response in assets.items():
        assert re.fullmatch(
            r"/admin/assets/[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.(?:js|css)", path
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/javascript" if path.endswith(".js") else "text/css"
        )
    assert all(response.status_code == 404 for response in removed_assets)
    assert protected.status_code == 401
    assert authorized.status_code == 200


def test_wheel_contains_only_the_vite_admin_distribution(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    server_root = project_root / "server"
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=server_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    source_dist = server_root / "src" / "agent_shell" / "frontend_dist"
    expected = {
        "agent_shell/frontend_dist/" + path.relative_to(source_dist).as_posix()
        for path in source_dist.rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(wheels[0]) as archive:
        packaged = set(archive.namelist())

    assert expected
    assert expected <= packaged
    assert not any(path.startswith("agent_shell/frontend/") for path in packaged)


def test_automatic_fastapi_documentation_is_not_registered(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        responses = [client.get(path) for path in ("/openapi.json", "/docs", "/redoc")]

    assert all(response.status_code == 404 for response in responses)


def test_local_management_password_blocks_cross_site_state_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", MANAGEMENT_TOKEN)

    with TestClient(create_app()) as client:
        before = client.get(
            "/api/api-server", headers=_bearer(MANAGEMENT_TOKEN)
        ).json()["enabled"]
        target = "/api/api-server/stop" if before else "/api/api-server/start"
        attack = client.post(
            target,
            headers={
                "Origin": "https://evil.example",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content=b"x",
        )
        after = client.get(
            "/api/api-server", headers=_bearer(MANAGEMENT_TOKEN)
        ).json()["enabled"]

    assert attack.status_code == 401
    assert before == after


def test_api_key_remains_independent_from_management_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", MANAGEMENT_TOKEN)
    page_key = "api-test-secret"

    with TestClient(create_app()) as client:
        saved = client.put(
            "/api/api-server",
            headers=_bearer(MANAGEMENT_TOKEN),
            json={"api_key": {"operation": "replace", "value": page_key}},
        )
        missing = client.get("/v1/models")
        wrong_scope = client.get(
            "/v1/models", headers=_bearer(MANAGEMENT_TOKEN)
        )
        allowed = client.get("/v1/models", headers=_bearer(page_key))

    assert saved.status_code == 200
    assert saved.json()["api_key"] == {"configured": True}
    assert missing.status_code == 401
    assert wrong_scope.status_code == 403
    assert allowed.status_code == 200


def test_remote_mode_accepts_the_user_chosen_api_key_without_a_minimum_length(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    chosen_key = "~"

    with TestClient(create_app()) as client:
        accepted = client.put(
            "/api/api-server",
            headers=_bearer(MANAGEMENT_TOKEN),
            json={"api_key": {"operation": "replace", "value": chosen_key}},
        )

    assert accepted.status_code == 200
    assert accepted.json()["api_key"] == {"configured": True}
    assert chosen_key not in accepted.text


def test_api_key_has_no_application_length_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    chosen_key = "k" * 5000

    with TestClient(create_app()) as client:
        accepted = client.put(
            "/api/api-server",
            headers=_bearer(MANAGEMENT_TOKEN),
            json={"api_key": {"operation": "replace", "value": chosen_key}},
        )
        authorized = client.get("/v1/models", headers=_bearer(chosen_key))

    assert accepted.status_code == 200
    assert authorized.status_code == 200
    assert chosen_key not in accepted.text


def test_remote_mode_requires_the_single_persisted_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell.settings import SettingsError

    _configure_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    with pytest.raises(SettingsError) as captured:
        create_app()

    assert captured.value.keys == ("API Server API Key",)
    assert "Remote access requires an API Key" in str(captured.value)


def test_remote_mode_cannot_clear_the_persisted_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")

    with TestClient(create_app()) as client:
        response = client.put(
            "/api/api-server",
            headers=_bearer(MANAGEMENT_TOKEN),
            json={"api_key": {"operation": "clear"}},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "api_key_required"


def test_startup_accepts_a_persisted_api_key_equal_to_management_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_paths(monkeypatch, tmp_path)
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    ApiServerStore(database).update_settings(
        api_key_operation="replace",
        api_key=MANAGEMENT_TOKEN,
    )

    with TestClient(create_app()) as client:
        management = client.get(
            "/api/api-server", headers=_bearer(MANAGEMENT_TOKEN)
        )
        inference = client.get("/v1/models", headers=_bearer(MANAGEMENT_TOKEN))

    assert management.status_code == 200
    assert inference.status_code == 200


def test_api_key_can_match_the_management_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_paths(monkeypatch, tmp_path)
    with TestClient(create_app()) as client:
        saved = client.put(
            "/api/api-server",
            headers=_bearer(MANAGEMENT_TOKEN),
            json={"api_key": {"operation": "replace", "value": MANAGEMENT_TOKEN}},
        )
        inference = client.get("/v1/models", headers=_bearer(MANAGEMENT_TOKEN))

    assert saved.status_code == 200
    assert saved.json()["api_key"] == {"configured": True}
    assert inference.status_code == 200


def test_management_and_api_scopes_are_independent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    app = create_app()

    @app.get("/api/whoami")
    async def whoami(request: Request) -> dict[str, object]:
        principal = request.state.principal
        return {
            "scope": principal.scope,
            "authenticated": principal.authenticated,
            "subject": principal.subject,
        }

    with TestClient(app) as client:
        management = client.get("/api/whoami", headers=_bearer(MANAGEMENT_TOKEN))
        wrong_management_scope = client.get(
            "/api/catalog", headers=_bearer(API_KEY)
        )
        api_namespace = client.get(
            "/v1/not-implemented", headers=_bearer(API_KEY)
        )
        wrong_api_scope = client.get(
            "/v1/not-implemented", headers=_bearer(MANAGEMENT_TOKEN)
        )

    assert management.json() == {
        "scope": "management",
        "authenticated": True,
        "subject": "management-token",
    }
    assert wrong_management_scope.status_code == 403
    assert wrong_management_scope.json()["error"]["code"] == "insufficient_scope"
    assert api_namespace.status_code == 404
    assert wrong_api_scope.status_code == 403
    assert wrong_api_scope.json()["error"]["code"] == "insufficient_scope"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer  two-spaces"},
        {"Authorization": "Bearer wrong-secret"},
        {"Authorization": "Bearer " + "a" * 8200},
    ],
)
def test_invalid_bearer_forms_use_stable_401_without_echo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    headers: dict[str, str],
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        response = client.get("/api/catalog", headers=headers)

    payload = response.json()
    assert response.status_code == 401
    assert payload["error"] == {
        "message": "A valid Bearer token is required.",
        "type": "authentication_error",
        "param": None,
        "code": "invalid_api_key",
        "message_key": "errors.invalidManagementCredential",
        "message_args": {},
    }
    assert payload["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == payload["request_id"]
    assert 'error="invalid_token"' in response.headers["www-authenticate"]
    assert "wrong-secret" not in response.text


def test_bearer_parser_rejects_delete_control_character() -> None:
    scope = {"headers": [(b"authorization", b"Bearer invalid\x7fvalue")]}

    with pytest.raises(SecurityFailure) as raised:
        _parse_bearer(scope)

    assert raised.value.status_code == 401
    assert raised.value.code == "invalid_api_key"


def test_duplicate_authorization_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/catalog",
            headers=[
                ("Authorization", f"Bearer {MANAGEMENT_TOKEN}"),
                ("Authorization", f"Bearer {MANAGEMENT_TOKEN}"),
            ],
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_authentication_stops_before_route_or_upstream_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    called = False
    app = create_app()

    @app.get("/api/auth-order/{item_id}")
    async def auth_order(item_id: str) -> dict[str, str]:
        nonlocal called
        called = True
        return {"item_id": item_id}

    with TestClient(app) as client:
        response = client.get("/api/auth-order/sensitive-item")

    assert response.status_code == 401
    assert called is False
    assert "sensitive-item" not in response.text


def test_valid_cors_preflight_does_not_require_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_CORS_ORIGINS", "https://console.example")

    with TestClient(create_app()) as client:
        response = client.options(
            "/api/catalog",
            headers={
                "Origin": "https://console.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, X-Request-ID",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://console.example"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_allowed_cors_origin_can_read_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_CORS_ORIGINS", "https://console.example")

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/catalog",
            headers={"Origin": "https://console.example"},
        )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://console.example"
    assert response.json()["error"]["code"] == "invalid_api_key"


def test_client_request_id_is_validated_and_returned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)

    with TestClient(create_app()) as client:
        accepted = client.get(
            "/api/catalog",
            headers={**_bearer(MANAGEMENT_TOKEN), "X-Request-ID": "client_req-123"},
        )
        replaced = client.get(
            "/api/catalog",
            headers={**_bearer(MANAGEMENT_TOKEN), "X-Request-ID": "bad value"},
        )

    assert accepted.headers["x-request-id"] == "client_req-123"
    assert replaced.headers["x-request-id"].startswith("req_")


def _configure_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    monkeypatch.setenv("AGENT_SHELL_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")


def _proxy_inspection_app() -> object:
    app = create_app()

    @app.get("/inspect-proxy")
    async def inspect_proxy(request: Request) -> dict[str, object]:
        return {
            "client": request.client.host if request.client else None,
            "scheme": request.url.scheme,
            "host": request.headers.get("host"),
        }

    return app


def test_proxy_headers_are_ignored_when_no_proxy_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_paths(monkeypatch, tmp_path)
    app = _proxy_inspection_app()

    with TestClient(app, client=("192.0.2.20", 5000)) as client:
        response = client.get(
            "/inspect-proxy",
            headers={
                "X-Forwarded-For": "198.51.100.7",
                "X-Forwarded-Proto": "https",
            },
        )

    assert response.json() == {
        "client": "192.0.2.20",
        "scheme": "http",
        "host": "testserver",
    }


def test_trusted_x_forwarded_chain_sets_only_validated_request_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_trusted_proxy(monkeypatch, tmp_path)
    app = _proxy_inspection_app()

    with TestClient(app, client=("10.2.0.4", 5000)) as client:
        response = client.get(
            "/inspect-proxy",
            headers={
                "X-Forwarded-For": "198.51.100.7, 10.1.0.3",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "Console.Example:8443",
            },
        )

    assert response.json() == {
        "client": "198.51.100.7",
        "scheme": "https",
        "host": "console.example:8443",
    }


def test_standard_forwarded_header_is_supported_from_trusted_peer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_trusted_proxy(monkeypatch, tmp_path)
    app = _proxy_inspection_app()

    with TestClient(app, client=("10.2.0.4", 5000)) as client:
        response = client.get(
            "/inspect-proxy",
            headers={
                "Forwarded": (
                    "for=198.51.100.8;proto=https;host=public.example, "
                    "for=10.1.0.3;proto=https;host=public.example"
                )
            },
        )

    assert response.json() == {
        "client": "198.51.100.8",
        "scheme": "https",
        "host": "public.example",
    }


@pytest.mark.parametrize(
    ("direct_client", "headers"),
    [
        (("192.0.2.20", 5000), {"X-Forwarded-For": "198.51.100.7"}),
        (
            ("10.2.0.4", 5000),
            {"Forwarded": "for=198.51.100.7", "X-Forwarded-For": "198.51.100.7"},
        ),
        (("10.2.0.4", 5000), {"X-Forwarded-Proto": "https"}),
        (
            ("10.2.0.4", 5000),
            {"X-Forwarded-For": "not-an-ip", "X-Forwarded-Proto": "https"},
        ),
        (
            ("10.2.0.4", 5000),
            {"X-Forwarded-For": "198.51.100.7", "X-Forwarded-Port": "443"},
        ),
    ],
)
def test_invalid_or_untrusted_proxy_headers_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    direct_client: tuple[str, int],
    headers: dict[str, str],
) -> None:
    _configure_trusted_proxy(monkeypatch, tmp_path)
    app = _proxy_inspection_app()

    with TestClient(app, client=direct_client) as client:
        response = client.get("/inspect-proxy", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_proxy_headers"
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert "198.51.100.7" not in response.text


def test_management_proxy_error_exposes_a_localization_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_trusted_proxy(monkeypatch, tmp_path)
    monkeypatch.setenv("AGENT_SHELL_CORS_ORIGINS", "https://console.example")

    with TestClient(create_app(), client=("10.2.0.4", 5000)) as client:
        response = client.get(
            "/api/catalog",
            headers={
                "Origin": "https://console.example",
                "X-Forwarded-For": "not-an-ip",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["message_key"] == "errors.invalidProxyHeaders"
    assert response.json()["error"]["message_args"] == {}
    assert response.headers["access-control-allow-origin"] == "https://console.example"
