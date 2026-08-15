from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from langchain.agents.middleware import ModelCallLimitMiddleware

from agent_shell.middleware_packages.runtime import MiddlewareOwner, MiddlewarePackageRuntime
from agent_shell.runtime.errors import AgentRuntimeError

from .support import make_client, middleware_config_schema


OWNER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def write_middleware_template(
    tmp_path: Path,
    *,
    source: str,
    config_schema: dict[str, object] | None = None,
    key: str = "request-label",
) -> Path:
    folder = tmp_path / "data" / "templates" / "agent" / "custom_middleware" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "family": "middleware",
                "adapter": "agent-middleware",
                "name": "Request label",
                "description": "Test middleware template.",
                "config_schema": config_schema
                or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")
    return folder


def write_private_middleware(
    tmp_path: Path,
    package_id: str,
    source: str,
    *,
    owner_id: str = OWNER_ID,
    config_schema: dict[str, object] | None = None,
) -> tuple[str, Path]:
    folder_name = f"{owner_id}--request-label--{package_id}"
    folder = (
        tmp_path
        / "data"
        / "config"
        / "python_package_instances"
        / "agent-middleware"
        / folder_name
    )
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": package_id,
                "family": "middleware",
                "adapter": "agent-middleware",
                "name": "Request label",
                "description": "Test middleware package.",
                "config_schema": config_schema
                or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")
    return folder_name, folder


def test_middleware_template_catalog_and_private_config_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class RequestLabel(AgentMiddleware):\n"
        "    pass\n"
        "def create_middleware(config, agent):\n"
        "    return RequestLabel()\n"
    )
    write_middleware_template(
        tmp_path,
        source=source,
        config_schema=middleware_config_schema(
            {"label": "string"}, required=("label",)
        ),
    )

    with make_client(tmp_path, monkeypatch) as client:
        catalog = client.get("/api/python-package-templates/middleware")
        selected = catalog.json()["catalog"][0]
        invalid = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Invalid package config",
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": selected["main_source"],
                    "requirements_source": selected["requirements_source"],
                },
            },
        )

    assert catalog.status_code == 200
    assert [item["key"] for item in catalog.json()["catalog"]] == ["request-label"]
    assert "dependency_status" not in catalog.json()["catalog"][0]
    assert invalid.status_code == 422
    assert any(
        issue["code"] == "python_package.config_invalid"
        for issue in invalid.json()["detail"]["validation"]["issues"]
    )


def test_missing_private_middleware_is_rejected_when_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "def create_middleware(config, agent):\n"
        "    return AgentMiddleware()\n"
    )
    write_middleware_template(tmp_path, source=source)
    with make_client(tmp_path, monkeypatch) as client:
        selected = client.get("/api/python-package-templates/middleware").json()["catalog"][0]
        created = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Missing package",
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": selected["main_source"],
                    "requirements_source": "",
                },
            },
        )
        assert created.status_code == 200, created.text
        folder = created.json()["python_package"]["folder"]
        shutil.rmtree(
            tmp_path
            / "data"
            / "config"
            / "python_package_instances"
            / "agent-middleware"
            / folder
        )
        response = client.get(f"/api/blocks/custom-middleware/{created.json()['id']}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "python_package_not_found"


def test_package_materializes_official_langchain_middleware(tmp_path: Path) -> None:
    folder_name, _folder = write_private_middleware(
        tmp_path,
        "33333333-3333-4333-8333-333333333333",
        "from langchain.agents.middleware import ModelCallLimitMiddleware\n"
        "def create_middleware(config, agent):\n"
        "    return ModelCallLimitMiddleware(run_limit=config['limit'])\n",
        config_schema=middleware_config_schema(
            {"limit": "integer"}, required=("limit",)
        ),
    )
    runtime = MiddlewarePackageRuntime(
        request_id="request-1",
        owners=[
            MiddlewareOwner(
                id="main",
                type="main_agent",
                name="Main",
                package_owner_id=OWNER_ID,
                package={"folder": folder_name, "config": {"limit": 2}},
            )
        ],
        packages_dir=tmp_path / "data" / "config" / "python_package_instances",
        runtime_root=tmp_path / "runtime",
    )

    materialized = runtime.middleware_for("main")

    assert len(materialized) == 1
    assert isinstance(materialized[0], ModelCallLimitMiddleware)
    asyncio.run(runtime.close())


def test_async_agent_runtime_rejects_sync_only_middleware_hooks(tmp_path: Path) -> None:
    folder_name, _folder = write_private_middleware(
        tmp_path,
        "55555555-5555-4555-8555-555555555555",
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class SyncOnly(AgentMiddleware):\n"
        "    def before_agent(self, state, runtime):\n"
        "        return None\n"
        "def create_middleware(config, agent):\n"
        "    return SyncOnly()\n",
    )
    runtime = MiddlewarePackageRuntime(
        request_id="request-1",
        owners=[
            MiddlewareOwner(
                id="main",
                type="main_agent",
                name="Main",
                package_owner_id=OWNER_ID,
                package={"folder": folder_name, "config": {}},
            )
        ],
        packages_dir=tmp_path / "data" / "config" / "python_package_instances",
        runtime_root=tmp_path / "runtime",
    )

    with pytest.raises(AgentRuntimeError) as caught:
        runtime.middleware_for("main")

    assert caught.value.code == "middleware_package_async_hook_required"
    assert caught.value.safe_message.endswith("before_agent without abefore_agent.")
    asyncio.run(runtime.close())
