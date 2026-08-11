from __future__ import annotations

from .support import *


def test_middleware_package_catalog_and_binding_schema_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_middleware_package(
        tmp_path,
        "request-label",
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
        catalog = client.get("/api/middlewares/custom")
        invalid = client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "Invalid package config",
                "middlewares": [
                    {
                        "package_id": "request-label",
                        "enabled": True,
                        "config": {},
                    }
                ],
            },
        )

    assert catalog.status_code == 200
    assert [item["id"] for item in catalog.json()["catalog"]] == ["request-label"]
    assert catalog.json()["catalog"][0]["dependency_status"] == "ready"
    assert invalid.status_code == 422
    assert any(
        issue["code"] == "middleware_package.config_invalid"
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
                "middlewares": [
                    {
                        "package_id": "missing-package",
                        "enabled": True,
                        "config": {},
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["validation"]["issues"][0]["code"] == (
        "middleware_package.not_found"
    )
