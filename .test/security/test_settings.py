from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_shell.app import create_app
from agent_shell.settings import SettingsError, get_settings
from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage import permissions as storage_permissions
from agent_shell.storage.permissions import PermissionStatus


def _write_environment_file(root: Path, content: str) -> Path:
    path = root / "data" / "config" / "agent-shell.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clean_agent_shell_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in tuple(os.environ):
        if key.upper().startswith("AGENT_SHELL_"):
            monkeypatch.delenv(key, raising=False)


def test_default_settings_require_a_management_password() -> None:
    with pytest.raises(SettingsError) as captured:
        get_settings()

    assert captured.value.keys == ("AGENT_SHELL_MANAGEMENT_TOKEN",)


def test_existing_environment_file_must_have_private_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_environment_file(
        tmp_path,
        "AGENT_SHELL_MANAGEMENT_TOKEN=management-secret\n",
    )
    monkeypatch.setattr(
        "agent_shell.app.secure_file",
        lambda path: PermissionStatus(
            "file",
            False,
            "test-unconfirmed",
            "The test did not confirm private permissions.",
        ),
    )

    with pytest.raises(SettingsError) as captured:
        create_app()

    assert captured.value.keys == ("data/config/agent-shell.env",)
    assert "management-secret" not in str(captured.value)


def test_local_settings_writer_secures_environment_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    environment_path = tmp_path / "agent-shell.env"
    secured: list[Path] = []
    monkeypatch.setattr(
        launcher,
        "secure_file",
        lambda path: (
            secured.append(path)
            or PermissionStatus(
                "file",
                True,
                "test-private",
                "The test confirmed private permissions.",
            )
        ),
    )

    launcher._write_management_password(
        "management-secret",
        env_path=environment_path,
        example_path=tmp_path / ".env.example",
    )

    assert secured == [environment_path]
    assert environment_path.read_text(encoding="utf-8") == (
        "AGENT_SHELL_MANAGEMENT_TOKEN=management-secret\n"
    )


def test_local_settings_writer_fails_when_permissions_cannot_be_secured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    environment_path = tmp_path / "agent-shell.env"
    monkeypatch.setattr(
        launcher,
        "secure_file",
        lambda path: PermissionStatus(
            "file",
            False,
            "test-unconfirmed",
            "The test did not confirm private permissions.",
        ),
    )

    with pytest.raises(OSError, match="permissions are not private"):
        launcher._write_management_password(
            "management-secret",
            env_path=environment_path,
            example_path=tmp_path / ".env.example",
        )

    assert environment_path.exists()


def test_docker_initializer_writes_each_credential_to_its_domain_store(
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    answers = iter(("m", "m", "m", "m"))

    result = launcher.initialize_docker_settings(
        application_home=tmp_path,
        data_root=tmp_path / "data",
        password_reader=lambda _prompt: next(answers),
    )

    assert result == 0
    environment = (tmp_path / "data" / "config" / "agent-shell.env").read_text(
        encoding="utf-8"
    )
    assert "AGENT_SHELL_MANAGEMENT_TOKEN=m" in environment
    assert "API_KEY" not in environment
    assert "INFERENCE" not in environment
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    assert ApiServerStore(database).api_key() == "m"


def test_docker_initializer_prompts_for_missing_persisted_api_key(
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    _write_environment_file(
        tmp_path,
        "AGENT_SHELL_HOST=0.0.0.0\n"
        "AGENT_SHELL_ALLOW_REMOTE=true\n"
        "AGENT_SHELL_MANAGEMENT_TOKEN=m\n",
    )
    answers = iter(("k", "k"))

    result = launcher.initialize_docker_settings(
        application_home=tmp_path,
        data_root=tmp_path / "data",
        password_reader=lambda _prompt: next(answers),
    )

    assert result == 0
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    assert ApiServerStore(database).api_key() == "k"


def test_local_management_password_does_not_require_an_api_key_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "management-secret")
    settings = get_settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 19100
    assert settings.is_loopback is True
    assert settings.deployment_mode == "authenticated_local"
    assert settings.cors_origins == ()
    assert settings.trusted_proxy_cidrs == ()
    assert "management-secret" not in repr(settings)


def test_unknown_prefixed_setting_fails_without_echoing_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "must-not-appear"
    monkeypatch.setenv("AGENT_SHELL_MANAGMENT_TOKEN", sentinel)

    with pytest.raises(SettingsError) as captured:
        get_settings()

    message = str(captured.value)
    assert "AGENT_SHELL_MANAGMENT_TOKEN" in message
    assert sentinel not in message


def test_unknown_prefixed_file_setting_fails_but_unrelated_setting_is_ignored(
    tmp_path: Path,
) -> None:
    _write_environment_file(
        tmp_path,
        "UNRELATED_SETTING=ignored\n"
        "AGENT_SHELL_MANAGMENT_TOKEN=must-not-appear\n",
    )

    with pytest.raises(SettingsError) as captured:
        get_settings(
            application_home=tmp_path,
            include_process_environment=False,
        )

    assert captured.value.keys == ("AGENT_SHELL_MANAGMENT_TOKEN",)
    assert "must-not-appear" not in str(captured.value)


def test_portable_settings_ignore_host_agent_shell_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_environment_file(
        tmp_path,
        "AGENT_SHELL_PORT=9123\n"
        "AGENT_SHELL_MANAGEMENT_TOKEN=portable-management-secret\n",
    )
    monkeypatch.setenv("AGENT_SHELL_PORT", "not-a-port")
    monkeypatch.setenv("AGENT_SHELL_MANAGMENT_TOKEN", "host-typo-secret")

    settings = get_settings(
        application_home=tmp_path,
        include_process_environment=False,
    )

    assert settings.port == 9123
    assert settings.management_token is not None
    assert settings.management_token.get_secret_value() == "portable-management-secret"


def test_relative_paths_are_bound_to_explicit_application_home(tmp_path: Path) -> None:
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"
    first_home.mkdir()
    second_home.mkdir()
    for home in (first_home, second_home):
        _write_environment_file(
            home,
            "AGENT_SHELL_MANAGEMENT_TOKEN=portable-management-secret\n",
        )

    first = get_settings(
        application_home=first_home,
        include_process_environment=False,
    )
    second = get_settings(
        application_home=second_home,
        include_process_environment=False,
    )

    assert first.resolved_database_path() == (
        first_home / "data" / "state" / "agent-shell.sqlite3"
    ).resolve()
    assert first.resolved_runtime_dir() == (first_home / "runtime").resolve()
    assert first.resolved_logs_dir() == (first_home / "data" / "logs").resolve()
    assert first.resolved_files_dir() == (first_home / "data" / "files").resolve()
    assert first.resolved_skills_dir() == (
        first_home / "data" / "resources" / "skills"
    ).resolve()
    assert second.resolved_database_path() == (
        second_home / "data" / "state" / "agent-shell.sqlite3"
    ).resolve()
    assert first.resolved_database_path() != second.resolved_database_path()


@pytest.mark.parametrize("host", ["127.99.1.2", "::1"])
def test_all_contract_loopback_addresses_allow_authenticated_local_mode(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_HOST", host)
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "management-secret")
    assert get_settings().deployment_mode == "authenticated_local"


def test_non_loopback_requires_explicit_remote_and_management_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_HOST", "0.0.0.0")

    with pytest.raises(SettingsError) as captured:
        get_settings()

    assert "AGENT_SHELL_ALLOW_REMOTE" in str(captured.value)
    assert "AGENT_SHELL_MANAGEMENT_TOKEN" in str(captured.value)


def test_remote_settings_accept_a_user_chosen_management_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_HOST", "0.0.0.0")
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "m")

    settings = get_settings()

    assert settings.deployment_mode == "authenticated_remote"
    assert settings.management_token is not None
    assert settings.management_token.get_secret_value() == "m"


def test_local_mode_keeps_a_user_chosen_management_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "m")

    settings = get_settings()

    assert settings.deployment_mode == "authenticated_local"


def test_management_password_has_no_application_length_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chosen_password = "m" * 5000
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", chosen_password)

    settings = get_settings()

    assert settings.management_token is not None
    assert settings.management_token.get_secret_value() == chosen_password


def test_bearer_tokens_reject_non_ascii_values_without_echo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "management-secrét"
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", token)

    with pytest.raises(SettingsError) as captured:
        get_settings()

    assert captured.value.keys == ("AGENT_SHELL_MANAGEMENT_TOKEN",)
    assert token not in str(captured.value)


def test_cors_and_proxy_lists_are_strict_and_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENT_SHELL_CORS_ORIGINS",
        '["https://EXAMPLE.com:8443", "http://127.0.0.1:3000"]',
    )
    monkeypatch.setenv("AGENT_SHELL_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,::1/128")
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "m")

    settings = get_settings()

    assert settings.cors_origins == (
        "https://example.com:8443",
        "http://127.0.0.1:3000",
    )
    assert settings.trusted_proxy_cidrs == ("10.0.0.0/8", "::1/128")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("AGENT_SHELL_HOST", "localhost"),
        ("AGENT_SHELL_PORT", "0"),
        ("AGENT_SHELL_CORS_ORIGINS", "*"),
        ("AGENT_SHELL_CORS_ORIGINS", "https://example.com/path"),
        ("AGENT_SHELL_TRUSTED_PROXY_CIDRS", "10.0.0.1/8"),
    ],
)
def test_invalid_network_settings_report_only_the_setting_key(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "management-secret")
    monkeypatch.setenv(key, value)

    with pytest.raises(SettingsError) as captured:
        get_settings()

    assert key in str(captured.value)
    assert value not in str(captured.value)


def test_create_app_installs_minimal_cors_and_runtime_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    data_root = tmp_path / "data"
    middleware_dir = data_root / "resources" / "custom_middlewares"
    monkeypatch.setenv("AGENT_SHELL_CORS_ORIGINS", "https://console.example")
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "management-secret")

    with TestClient(create_app()) as client:
        allowed = client.options(
            "/api/catalog",
            headers={
                "Origin": "https://console.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, X-Request-ID",
            },
        )
        rejected = client.options(
            "/api/catalog",
            headers={
                "Origin": "https://other.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://console.example"
    assert "access-control-allow-credentials" not in allowed.headers
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
    assert (runtime_dir / "cache").is_dir()
    assert (runtime_dir / "tmp").is_dir()
    assert (runtime_dir / "home").is_dir()
    assert (data_root / "state").is_dir()
    assert (data_root / "files").is_dir()
    assert (data_root / "logs").is_dir()
    assert middleware_dir.is_dir()


def test_official_launcher_uses_only_validated_settings_and_disables_proxy_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent_shell import __main__ as launcher

    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setenv("AGENT_SHELL_HOST", "127.0.0.2")
    monkeypatch.setenv("AGENT_SHELL_PORT", "9123")
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", "management-secret")
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert launcher.main(serve_frontend=False) == 0
    assert len(calls) == 1
    assert calls[0][0][0].title == "agent-shell"
    assert calls[0][1] == {
        "host": "127.0.0.2",
        "port": 9123,
        "proxy_headers": False,
        "ws": "websockets-sansio",
    }


def test_official_launcher_prints_effective_settings_for_windows_script(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    _write_environment_file(
        tmp_path,
        "AGENT_SHELL_HOST=::1\n"
        "AGENT_SHELL_PORT=9123\n"
        "AGENT_SHELL_MANAGEMENT_TOKEN=management-secret\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda *args, **kwargs: pytest.fail("settings query must not start uvicorn"),
    )

    assert (
        launcher.run_cli(
            ["--home", str(tmp_path), "--print-launch-settings"]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out == "::1|9123|http://[::1]:9123/admin\n"
    assert captured.err == ""


def test_official_launcher_warns_when_remote_http_backend_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    management_token = "management-secret-sentinel"
    api_key = "api-secret-sentinel"
    monkeypatch.setenv("AGENT_SHELL_ALLOW_REMOTE", "true")
    monkeypatch.setenv("AGENT_SHELL_MANAGEMENT_TOKEN", management_token)
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    ApiServerStore(database).update_settings(
        api_key_operation="replace",
        api_key=api_key,
    )
    monkeypatch.setattr(launcher.uvicorn, "run", lambda *_args, **_kwargs: None)

    assert launcher.main(serve_frontend=False) == 0
    captured = capsys.readouterr()
    assert "Remote HTTP backend enabled" in captured.err
    assert "TLS reverse proxy and firewall" in captured.err
    assert management_token not in captured.err
    assert api_key not in captured.err


def test_official_launcher_reports_safe_startup_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agent_shell import __main__ as launcher

    sentinel = "launcher-inference-secret"
    monkeypatch.setenv("AGENT_SHELL_INFERENCE_TOKEN", sentinel)
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda *args, **kwargs: pytest.fail(
            "invalid settings must not start uvicorn"
        ),
    )

    assert launcher.main() == 2
    captured = capsys.readouterr()
    assert "AGENT_SHELL_INFERENCE_TOKEN" in captured.err
    assert sentinel not in captured.err


def test_windows_launcher_initializes_missing_local_management_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    sentinel = "local-admin-2026"
    (tmp_path / ".env.example").write_text(
        "AGENT_SHELL_HOST=127.0.0.1\n"
        "AGENT_SHELL_PORT=9123\n"
        "# AGENT_SHELL_MANAGEMENT_TOKEN=<generate-a-management-token>\n",
        encoding="utf-8",
    )
    answers = iter((sentinel, sentinel))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher.getpass, "getpass", lambda _prompt: next(answers))

    result = launcher.run_cli(
        ["--home", str(tmp_path), "--initialize-local-settings"]
    )
    if result != 0:
        env_path = tmp_path / "data" / "config" / "agent-shell.env"
        permission = launcher.secure_file(env_path)
        dacl = storage_permissions._read_windows_dacl(env_path)
        pytest.fail(
            "local settings initialization failed: "
            f"env_exists={env_path.exists()}, "
            f"permission={permission.mechanism}/{permission.boundary}, "
            f"dacl={dacl or '<unreadable>'}"
        )

    env_text = (
        tmp_path / "data" / "config" / "agent-shell.env"
    ).read_text(encoding="utf-8")
    assert "AGENT_SHELL_HOST=127.0.0.1" in env_text
    assert "AGENT_SHELL_PORT=9123" in env_text
    assert f"AGENT_SHELL_MANAGEMENT_TOKEN={sentinel}" in env_text
    assert "# AGENT_SHELL_MANAGEMENT_TOKEN=" not in env_text
    assert get_settings().management_token.get_secret_value() == sentinel
    captured = capsys.readouterr()
    assert "不会改变 /v1 OpenAI API 使用的 Key" in captured.out
    assert sentinel not in captured.out
    assert captured.err == ""


def test_windows_launcher_keeps_existing_management_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    original = "AGENT_SHELL_MANAGEMENT_TOKEN=existing-admin-password\n"
    env_path = _write_environment_file(tmp_path, original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        launcher.getpass,
        "getpass",
        lambda _prompt: pytest.fail("an existing password must not be prompted for"),
    )

    assert (
        launcher.run_cli(
            ["--home", str(tmp_path), "--initialize-local-settings"]
        )
        == 0
    )
    assert env_path.read_text(encoding="utf-8") == original


def test_windows_launcher_does_not_overwrite_invalid_existing_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    original = "AGENT_SHELL_PORT=not-a-port\n"
    env_path = _write_environment_file(tmp_path, original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        launcher.getpass,
        "getpass",
        lambda _prompt: pytest.fail("invalid settings must not enter password setup"),
    )

    assert (
        launcher.run_cli(
            ["--home", str(tmp_path), "--initialize-local-settings"]
        )
        == 2
    )
    assert env_path.read_text(encoding="utf-8") == original
    captured = capsys.readouterr()
    assert "AGENT_SHELL_PORT" in captured.err
    assert "not-a-port" not in captured.err


def test_windows_launcher_does_not_initialize_remote_deployment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    original = (
        "AGENT_SHELL_HOST=0.0.0.0\n"
        "AGENT_SHELL_ALLOW_REMOTE=true\n"
    )
    env_path = _write_environment_file(tmp_path, original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        launcher.getpass,
        "getpass",
        lambda _prompt: pytest.fail("remote deployment must be configured explicitly"),
    )

    assert (
        launcher.run_cli(
            ["--home", str(tmp_path), "--initialize-local-settings"]
        )
        == 2
    )
    assert env_path.read_text(encoding="utf-8") == original
    captured = capsys.readouterr()
    assert "AGENT_SHELL_MANAGEMENT_TOKEN" in captured.err


def test_docker_initializer_creates_one_valid_remote_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    password = "admin"
    api_key = "api"
    answers = iter((password, password, api_key, api_key))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher.getpass, "getpass", lambda _prompt: next(answers))

    result = launcher.run_cli(
        ["--home", str(tmp_path), "--initialize-docker-settings"]
    )

    assert result == 0
    settings = get_settings(
        application_home=tmp_path,
        include_process_environment=False,
    )
    assert settings.host == "0.0.0.0"
    assert settings.port == 19100
    assert settings.allow_remote is True
    assert settings.management_token is not None
    assert settings.management_token.get_secret_value() == password
    store = ApiServerStore(
        SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    )
    assert store.api_key() == api_key
    assert api_key not in (
        tmp_path / "data" / "config" / "agent-shell.env"
    ).read_text(encoding="utf-8")


def test_docker_initializer_does_not_overwrite_invalid_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agent_shell import __main__ as launcher

    original = "AGENT_SHELL_PORT=invalid\n"
    env_path = _write_environment_file(tmp_path, original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        launcher.getpass,
        "getpass",
        lambda _prompt: pytest.fail("invalid existing settings must not be replaced"),
    )

    result = launcher.run_cli(
        ["--home", str(tmp_path), "--initialize-docker-settings"]
    )

    assert result == 2
    assert env_path.read_text(encoding="utf-8") == original
