from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import uvicorn

from agent_shell.automation.dependencies import activate_plugin_site
from agent_shell.app import create_app
from agent_shell.settings import (
    SettingsError,
    bearer_token_is_valid,
    get_settings,
    load_settings,
)
from agent_shell.storage.permissions import secure_file


_MISSING_LOCAL_MANAGEMENT_TOKEN_ACTION = "Configure the management Bearer token."


def _read_confirmed_credential(
    read_password: Callable[[str], str],
    *,
    prompt: str,
    confirmation_prompt: str,
    invalid_message: str,
) -> str | None:
    while True:
        try:
            value = read_password(prompt)
            confirmation = read_password(confirmation_prompt)
        except (EOFError, KeyboardInterrupt):
            return None
        if not bearer_token_is_valid(value):
            print(invalid_message)
            continue
        if value != confirmation:
            print("两次输入不一致，请重新输入。")
            continue
        return value


def listen_address_is_available(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_EXCLUSIVEADDRUSE,
                    1,
                )
            listener.bind((host, port))
    except OSError:
        return False
    return True


def _write_management_password(
    password: str,
    *,
    env_path: Path,
    example_path: Path,
) -> None:
    source_path = env_path if env_path.exists() else example_path
    if source_path.exists():
        with source_path.open("r", encoding="utf-8-sig", newline="") as source:
            existing = source.read()
    else:
        existing = ""

    newline = "\r\n" if "\r\n" in existing else "\n"
    lines = existing.splitlines()
    replacement = f"AGENT_SHELL_MANAGEMENT_TOKEN={password}"
    placeholder = re.compile(
        r"^\s*#\s*AGENT_SHELL_MANAGEMENT_TOKEN\s*=.*$",
        flags=re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        if placeholder.fullmatch(line):
            lines[index] = replacement
            break
    else:
        if lines and lines[-1]:
            lines.append("")
        lines.append(replacement)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="agent-shell.env.", suffix=".tmp", dir=env_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as target:
            target.write(newline.join(lines) + newline)
        os.replace(temporary_path, env_path)
        permission = secure_file(env_path)
        if not permission.enforced:
            raise OSError("The management settings file permissions are not private.")
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def initialize_local_settings(
    *,
    application_home: Path | None = None,
    data_root: Path | None = None,
    include_process_environment: bool = False,
    env_path: Path | None = None,
    example_path: Path | None = None,
    password_reader: Callable[[str], str] | None = None,
) -> int:
    home = (application_home or Path.cwd()).resolve()
    root = data_root or (home / "data")
    root = root.resolve() if root.is_absolute() else (home / root).resolve()
    env_path = env_path or root / "config" / "agent-shell.env"
    example_path = example_path or home / ".env.example"
    missing_management_error: SettingsError | None = None
    try:
        get_settings(
            application_home=home,
            data_root=root,
            include_process_environment=include_process_environment,
        )
    except SettingsError as exc:
        if not (
            exc.keys == ("AGENT_SHELL_MANAGEMENT_TOKEN",)
            and exc.action == _MISSING_LOCAL_MANAGEMENT_TOKEN_ACTION
        ):
            print(f"Startup configuration error: {exc}", file=sys.stderr)
            return 2
        missing_management_error = exc
    else:
        return 0

    try:
        current_settings = load_settings(
            application_home=home,
            data_root=root,
            include_process_environment=include_process_environment,
        )
    except SettingsError as exc:
        print(f"Startup configuration error: {exc}", file=sys.stderr)
        return 2
    if current_settings.deployment_mode != "authenticated_local":
        print(
            f"Startup configuration error: {missing_management_error}",
            file=sys.stderr,
        )
        return 2
    read_password = password_reader or getpass.getpass

    print("首次启动：请设置管理网站密码。")
    print("这个密码只用于打开管理网站，不会改变 /v1 OpenAI API 使用的 Key。")
    print("请输入不含空格的可打印 ASCII 字符。")
    password = _read_confirmed_credential(
        read_password,
        prompt="管理密码（输入时不会显示）：",
        confirmation_prompt="请再输入一次：",
        invalid_message="密码格式不对，请输入不含空格的可打印 ASCII 字符。",
    )
    if password is None:
        print("\n已取消，没有创建或修改配置文件。", file=sys.stderr)
        return 1

    try:
        _write_management_password(
            password,
            env_path=env_path,
            example_path=example_path,
        )
    except OSError:
        print("无法保存配置文件，请检查 data 目录是否可写。", file=sys.stderr)
        return 1

    print("管理密码已保存。以后双击 start_server.bat 会直接启动。")
    print()
    return 0


def main(
    *,
    application_home: Path | None = None,
    data_root: Path | None = None,
    include_process_environment: bool = True,
    print_launch_settings: bool = False,
    probe_listen_settings: bool = False,
    port_override: int | None = None,
    serve_frontend: bool = True,
) -> int:
    home = (application_home or Path.cwd()).resolve()
    try:
        settings = get_settings(
            application_home=home,
            data_root=data_root,
            include_process_environment=include_process_environment,
        )
    except SettingsError as exc:
        print(f"Startup configuration error: {exc}", file=sys.stderr)
        return 2
    if port_override is not None:
        settings.port = port_override

    if probe_listen_settings:
        if listen_address_is_available(settings.host, settings.port):
            return 0
        print(
            f"Configured listen address {settings.host}:{settings.port} "
            "cannot be bound. The port may be occupied or reserved by the OS.",
            file=sys.stderr,
        )
        return 3

    if print_launch_settings:
        display_host = f"[{settings.host}]" if ":" in settings.host else settings.host
        print(
            f"{settings.host}|{settings.port}|"
            f"http://{display_host}:{settings.port}/admin"
        )
        return 0

    if settings.deployment_mode == "authenticated_remote":
        print(
            "WARNING: Remote HTTP backend enabled. Publish it only behind a TLS "
            "reverse proxy and firewall.",
            file=sys.stderr,
        )

    activate_plugin_site(settings.resolved_runtime_dir())
    app = create_app(settings=settings, serve_frontend=serve_frontend)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        proxy_headers=False,
        ws="websockets-sansio",
    )
    return 0


def run_cli(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    parser = argparse.ArgumentParser(prog="python -m agent_shell")
    parser.add_argument(
        "--home",
        required=True,
        type=Path,
        help="Application home containing the program runtime.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Persistent data root. Relative paths are resolved from application home.",
    )
    parser.add_argument(
        "--mode",
        choices=("portable", "environment"),
        default="portable",
        help="Portable ignores host AGENT_SHELL_* variables; environment accepts them.",
    )
    parser.add_argument("--port", type=int, choices=range(1, 65536))
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--initialize-local-settings", action="store_true")
    action.add_argument("--print-launch-settings", action="store_true")
    action.add_argument("--probe-listen-settings", action="store_true")
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="Run only the API backend for the Vite development proxy.",
    )
    try:
        parsed = parser.parse_args(arguments)
    except SystemExit as exc:
        return int(exc.code)

    home = parsed.home.resolve()
    data_root = parsed.data_dir or (home / "data")
    data_root = (
        data_root.resolve()
        if data_root.is_absolute()
        else (home / data_root).resolve()
    )
    include_process_environment = parsed.mode == "environment"
    if parsed.initialize_local_settings:
        return initialize_local_settings(
            application_home=home,
            data_root=data_root,
            include_process_environment=include_process_environment,
        )
    return main(
        application_home=home,
        data_root=data_root,
        include_process_environment=include_process_environment,
        print_launch_settings=parsed.print_launch_settings,
        probe_listen_settings=parsed.probe_listen_settings,
        port_override=parsed.port,
        serve_frontend=not parsed.no_frontend,
    )


if __name__ == "__main__":
    raise SystemExit(run_cli())
