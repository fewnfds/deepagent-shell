from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any
from uuid import UUID

import httpx

from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.file_config import FileConfigRepository


CAPABILITY_TYPES = (
    "model",
    "system-prompt",
    "filesystem",
    "filesystem-permissions",
    "todo-list",
    "custom-tool",
    "skill",
    "custom-middleware",
    "output-mode",
    "exception-retry",
    "subagent",
    "summarization",
    "prompt-caching",
    "workflow-input-context",
)
OUTPUT_EVENT_TYPES = (
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "tool_error",
    "subagent",
    "custom",
    "lifecycle",
)
MODEL_PARAMETER_NAMES = (
    "temperature",
    "max_completion_tokens",
    "top_p",
    "stop_sequences",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "timeout",
    "max_retries",
    "stream_usage",
    "streaming",
    "reasoning_effort",
    "service_tier",
    "logprobs",
    "top_logprobs",
)


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _payload(capability_type: str, name: str, secret: str, *, update: bool) -> dict:
    model_parameters = dict.fromkeys(MODEL_PARAMETER_NAMES)
    if update:
        model_parameters.update(
            {
                "temperature": 0,
                "max_completion_tokens": 2048,
                "top_p": 0.9,
                "stop_sequences": ["END", "STOP"],
                "presence_penalty": 0,
                "frequency_penalty": 0,
                "seed": 42,
                "timeout": 30,
                "max_retries": 2,
                "stream_usage": True,
                "streaming": True,
                "reasoning_effort": "medium",
                "service_tier": "auto",
                "logprobs": False,
                "top_logprobs": 5,
            }
        )
    payloads = {
        "model": {
            "name": name,
            "provider": "openai",
            "base_url": "https://provider.example.invalid/v1",
            "credential": None if update else secret,
            "model": "smoke-model",
            "provider_settings": model_parameters,
            "tool_choice": None,
            "response_format": None,
            "model_settings": {},
        },
        "custom-tool": {"name": name, "tools": []},
        "custom-middleware": {"name": name, "python_package_bindings": []},
        "output-mode": {
            "name": name,
            "filter_mode": "blocklist",
            "filter_mappings": [],
            "event_outputs": {
                event_type: {
                    "enabled": True,
                    "output_source": 'def output(event):\n    return event["message"]\n',
                }
                for event_type in OUTPUT_EVENT_TYPES
            },
        },
        "filesystem": {"name": name},
        "filesystem-permissions": {
            "name": name,
            "permissions": [
                {"path": "/workspace/**", "permission": "read-only"}
            ],
        },
        "skill": {"name": name, "skills": ["fixture-skill"]},
        "system-prompt": {"name": name, "system_prompt": "Smoke prompt."},
        "subagent": {"name": name},
        "summarization": {"name": name},
        "prompt-caching": {"name": name},
        "workflow-input-context": {"name": name},
        "todo-list": {"name": name},
        "exception-retry": {
            "name": name,
            "strategy": "provider_native",
            "force_non_streaming": False,
            "max_retries": 2,
            "retry_on": ["transport_error", "timeout", "rate_limit", "server_error"],
        },
    }
    return payloads[capability_type]


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    expected: int = 200,
) -> httpx.Response:
    response = client.request(method, path, headers=headers, json=json_body)
    if response.status_code != expected:
        raise AssertionError(
            f"{method} {path}: expected {expected}, got {response.status_code}: {response.text}"
        )
    return response


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        process.kill()
    process.wait(timeout=8)


def _run_mode(repo_root: Path, scratch_root: Path) -> dict:
    mode = "authenticated"
    work = scratch_root / mode
    work.mkdir(parents=True, exist_ok=True)
    data_dir = work / "data"
    database_path = data_dir / "state" / "agent-shell.sqlite3"
    port = _port()
    management_token = secrets.token_urlsafe(32)
    api_key = secrets.token_urlsafe(32)
    provider_secret = "smoke-provider-" + secrets.token_urlsafe(24)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("AGENT_SHELL_")
    }
    environment["AGENT_SHELL_MANAGEMENT_TOKEN"] = management_token
    configuration = FileConfigRepository(data_dir)
    configuration.update_system(
        lambda system: system["settings"].update(
            {
                "host": "127.0.0.1",
                "port": port,
                "cors_origins": ["https://console.example.invalid"],
            }
        )
    )
    ApiServerStore(
        SQLiteDatabase(database_path), configuration
    ).update_settings(
        api_key_operation="replace",
        api_key=api_key,
    )
    output_path = work / "server-output.txt"
    output = output_path.open("wb")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_shell",
            "--home",
            str(work),
            "--data-dir",
            str(data_dir),
            "--mode",
            "environment",
        ],
        cwd=repo_root / "server",
        env=environment,
        stdout=output,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    base_url = f"http://127.0.0.1:{port}"
    management = {"Authorization": f"Bearer {management_token}"}
    inference = {"Authorization": f"Bearer {api_key}"}
    client = httpx.Client(base_url=base_url, timeout=3, trust_env=False)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                if client.get("/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise AssertionError("server exited before health became available")
            if time.monotonic() >= deadline:
                raise AssertionError("server did not become healthy")
            time.sleep(0.1)

        admin = _request(client, "GET", "/admin")
        admin_assets = set(
            re.findall(r'(?:src|href)="(/admin/assets/[^"]+)"', admin.text)
        )
        assert admin_assets
        assert not any(
            path.endswith(("/icons.js", "/api.js")) or "/vendor/" in path
            for path in admin_assets
        )
        for path in admin_assets:
            _request(client, "GET", path)
        health = _request(client, "GET", "/api/health").json()
        assert health == {"status": "ok", "runtime": "model_streaming"}
        _request(client, "GET", "/api/catalog", expected=401)
        _request(client, "GET", "/api/catalog", headers=inference, expected=403)
        _request(client, "GET", "/v1/unknown", headers=management, expected=403)
        _request(client, "GET", "/v1/unknown", headers=inference, expected=404)
        catalog = _request(client, "GET", "/api/catalog", headers=management).json()
        assert tuple(item["type"] for item in catalog["block_types"]) == CAPABILITY_TYPES
        _request(client, "GET", "/api/tools/custom", headers=management)
        _request(client, "GET", "/api/python-packages/middleware/agent-middleware", headers=management)
        _request(client, "GET", "/api/skills", headers=management)
        readiness = _request(
            client, "GET", "/api/readiness", headers=management
        ).json()
        assert set(readiness["sections"]) == {
            "security_settings",
            "storage",
            "runtime_dependencies",
        }
        assert readiness["sections"]["storage"]["status"] == (
            "startup_permissions_confirmed"
        )
        preflight = _request(
            client,
            "OPTIONS",
            "/api/catalog",
            headers={
                "Origin": "https://console.example.invalid",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, X-Request-ID",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == (
            "https://console.example.invalid"
        )

        blocks: dict[str, dict] = {}
        for capability_type in CAPABILITY_TYPES:
            created = _request(
                client,
                "POST",
                f"/api/blocks/{capability_type}",
                headers={**management, "X-Request-ID": f"smoke-{mode}"},
                json_body=_payload(
                    capability_type,
                    f"{mode}-{capability_type}",
                    provider_secret,
                    update=False,
                ),
            ).json()
            UUID(created["id"])
            assert provider_secret not in json.dumps(created)
            if capability_type == "model":
                assert created["provider_settings"] == {}
            blocks[capability_type] = created
            listed = _request(
                client, "GET", f"/api/blocks/{capability_type}", headers=management
            ).json()
            assert any(item["id"] == created["id"] for item in listed)
            fetched = _request(
                client,
                "GET",
                f"/api/blocks/{capability_type}/{created['id']}",
                headers=management,
            ).json()
            assert fetched["id"] == created["id"]
            updated = _request(
                client,
                "PUT",
                f"/api/blocks/{capability_type}/{created['id']}",
                headers=management,
                json_body=_payload(
                    capability_type,
                    f"{mode}-{capability_type}-updated",
                    provider_secret,
                    update=True,
                ),
            ).json()
            assert updated["id"] == created["id"]
            if capability_type == "model":
                assert updated["provider_settings"]["stop_sequences"] == [
                    "END",
                    "STOP",
                ]
                assert updated["provider_settings"]["streaming"] is True
                assert updated["provider_settings"]["stream_usage"] is True

        cleared_model_payload = _payload(
            "model",
            f"{mode}-model-updated",
            provider_secret,
            update=True,
        )
        cleared_model_payload["provider_settings"] = {}
        cleared_model = _request(
            client,
            "PUT",
            f"/api/blocks/model/{blocks['model']['id']}",
            headers=management,
            json_body=cleared_model_payload,
        ).json()
        assert cleared_model["provider_settings"] == {}

        main_agent = _request(
            client,
            "POST",
            "/api/main-agents",
            headers=management,
            json_body={
                "name": f"{mode}-main-agent",
                "capability_refs": [
                    {"type": "model", "block_id": blocks["model"]["id"]},
                    {
                        "type": "output-mode",
                        "block_id": blocks["output-mode"]["id"],
                    },
                ],
                "subagents": [],
            },
        ).json()
        subagent = _request(
            client,
            "POST",
            "/api/subagents",
            headers=management,
            json_body={
                "component_name": f"{mode}-subagent",
                "name": "smoke_worker",
                "description": "Handles smoke-test delegated work.",
                "settings": {
                    "capability_overrides": [],
                },
            },
        ).json()
        for path, item in (
            ("main-agents", main_agent),
            ("subagents", subagent),
        ):
            UUID(item["id"])
            _request(client, "GET", f"/api/{path}", headers=management)
            fetched = _request(
                client, "GET", f"/api/{path}/{item['id']}", headers=management
            ).json()
            assert fetched["id"] == item["id"]
        updated_main_agent = dict(main_agent)
        updated_main_agent.pop("id")
        updated_main_agent["name"] += "-updated"
        _request(
            client,
            "PUT",
            f"/api/main-agents/{main_agent['id']}",
            headers=management,
            json_body=updated_main_agent,
        )
        updated_subagent = dict(subagent)
        updated_subagent.pop("id")
        updated_subagent["component_name"] += "-updated"
        _request(
            client,
            "PUT",
            f"/api/subagents/{subagent['id']}",
            headers=management,
            json_body=updated_subagent,
        )

        model_id = blocks["model"]["id"]
        model_path = data_dir / "config" / "components" / "model" / f"{model_id}.yaml"
        model_text = model_path.read_text(encoding="utf-8")
        assert provider_secret not in model_text
        model_secret_name = f"AGENT_SHELL_MODEL_{model_id.replace('-', '').upper()}_API_KEY"
        assert f"credential: ${model_secret_name}" in model_text
        environment_text = (data_dir / "config" / "agent-shell.env").read_text(encoding="utf-8")
        assert f"{model_secret_name}={provider_secret}" in environment_text
        with closing(sqlite3.connect(database_path)) as connection, connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            assert not ({"blocks", "provider_secrets", "workflows"} & tables)
        event_path = data_dir / "logs" / "security-events.jsonl"
        event_text = event_path.read_text(encoding="utf-8")
        assert provider_secret not in event_text
        assert management_token not in event_text
        assert api_key not in event_text

        _request(
            client,
            "DELETE",
            f"/api/main-agents/{main_agent['id']}",
            headers=management,
        )
        _request(
            client,
            "DELETE",
            f"/api/subagents/{subagent['id']}",
            headers=management,
        )
        for capability_type, block in blocks.items():
            _request(
                client,
                "DELETE",
                f"/api/blocks/{capability_type}/{block['id']}",
                headers=management,
            )
        assert provider_secret not in (
            data_dir / "config" / "agent-shell.env"
        ).read_text(encoding="utf-8")
        assert f"{model_secret_name}=" not in (
            data_dir / "config" / "agent-shell.env"
        ).read_text(encoding="utf-8")
        return {
            "mode": mode,
            "capability_count": len(blocks),
            "readiness_sections": len(readiness["sections"]),
            "authenticated": True,
        }
    finally:
        client.close()
        _stop_process(process)
        output.close()
        if process.returncode not in {0, 1, -15}:
            raise AssertionError(f"server shutdown failed in {mode} mode")
        if output_path.exists():
            output_text = output_path.read_text(encoding="utf-8", errors="replace")
            for sentinel in (management_token, api_key, provider_secret):
                if sentinel in output_text:
                    raise AssertionError("server output contained a secret sentinel")
        # Windows can briefly retain a delete-denying handle after the child
        # process exits even though wait() has completed. Give the OS a small
        # release window before TemporaryDirectory removes the isolated run.
        if os.name == "nt":
            time.sleep(0.25)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    scratch_parent = repo_root / "runtime" / "tmp"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="security-http-smoke-", dir=scratch_parent
    ) as scratch:
        root = Path(scratch)
        reports = [_run_mode(repo_root, root)]
    leftovers = list(scratch_parent.glob("security-http-smoke-*"))
    if leftovers:
        raise AssertionError("security smoke left temporary artifacts")
    print(json.dumps({"status": "passed", "modes": reports}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
