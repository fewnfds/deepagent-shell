from __future__ import annotations

from .support import *

from agent_shell.middleware_packages.runtime import MiddlewareOwner, MiddlewarePackageRuntime
from agent_shell.runtime.errors import AgentRuntimeError
from langchain.agents.middleware import ModelCallLimitMiddleware


PACKAGE_ID = "11111111-1111-4111-8111-111111111111"


def test_middleware_package_catalog_and_binding_schema_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_middleware_package(
        tmp_path,
        PACKAGE_ID,
        "from langchain.agents.middleware import AgentMiddleware\n"
        "class RequestLabel(AgentMiddleware):\n"
        "    pass\n"
        "def create_middleware(config, agent):\n"
        "    return RequestLabel()\n",
        config_schema=middleware_config_schema(
            {"label": "string"},
            required=("label",),
        ),
    )

    with make_client(tmp_path, monkeypatch) as client:
        catalog = client.get("/api/python-packages/middleware/agent-middleware")
        invalid = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Invalid package config",
                "python_package_bindings": [
                    {
                        "package_id": PACKAGE_ID,
                        "enabled": True,
                        "config": {},
                    }
                ],
            },
        )

    assert catalog.status_code == 200
    assert [item["id"] for item in catalog.json()["catalog"]] == [PACKAGE_ID]
    assert catalog.json()["catalog"][0]["dependency_status"] == "ready"
    assert invalid.status_code == 422
    assert any(
        issue["code"] == "python_package.config_invalid"
        for issue in invalid.json()["detail"]["validation"]["issues"]
    )


def test_missing_middleware_package_is_rejected_before_agent_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        response = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Missing package",
                "python_package_bindings": [
                    {
                        "package_id": "22222222-2222-4222-8222-222222222222",
                        "enabled": True,
                        "config": {},
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["validation"]["issues"][0]["code"] == (
        "python_package.not_found"
    )


def test_package_materializes_official_langchain_middleware(tmp_path: Path) -> None:
    package_id = "33333333-3333-4333-8333-333333333333"
    write_middleware_package(
        tmp_path,
        package_id,
        "from langchain.agents.middleware import ModelCallLimitMiddleware\n"
        "def create_middleware(config, agent):\n"
        "    return ModelCallLimitMiddleware(run_limit=config['limit'])\n",
        config_schema=middleware_config_schema(
            {"limit": "integer"},
            required=("limit",),
        ),
    )
    runtime = MiddlewarePackageRuntime(
        request_id="request-1",
        owners=[
            MiddlewareOwner(
                id="main",
                type="main_agent",
                name="Main",
                bindings=(
                    {
                        "package_id": package_id,
                        "enabled": True,
                        "config": {"limit": 2},
                    },
                ),
            )
        ],
        packages_dir=tmp_path / "data" / "resources" / "python_packages",
        runtime_root=tmp_path / "runtime",
    )

    materialized = runtime.middleware_for("main")

    assert len(materialized) == 1
    assert isinstance(materialized[0], ModelCallLimitMiddleware)
    asyncio.run(runtime.close())


def test_async_agent_runtime_rejects_sync_only_middleware_hooks(tmp_path: Path) -> None:
    package_id = "55555555-5555-4555-8555-555555555555"
    write_middleware_package(
        tmp_path,
        package_id,
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
                bindings=(
                    {"package_id": package_id, "enabled": True, "config": {}},
                ),
            )
        ],
        packages_dir=tmp_path / "data" / "resources" / "python_packages",
        runtime_root=tmp_path / "runtime",
    )

    with pytest.raises(AgentRuntimeError) as caught:
        runtime.middleware_for("main")

    assert caught.value.code == "middleware_package_async_hook_required"
    assert caught.value.safe_message.endswith("before_agent without abefore_agent.")
    asyncio.run(runtime.close())
