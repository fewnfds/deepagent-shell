from __future__ import annotations

from pathlib import Path

from agent_shell.provider_integrations import (
    bundled_provider_integrations,
    official_provider_integrations,
)

from app_support import make_client


def test_langchain_registry_is_the_provider_package_authority() -> None:
    integrations = {item.provider: item for item in official_provider_integrations()}

    assert integrations["openrouter"].package == "langchain-openrouter"
    assert integrations["google_vertexai"].package == "langchain-google-vertexai"
    assert integrations["anthropic"].class_name == "ChatAnthropic"


def test_catalog_contains_only_release_managed_provider_integrations(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    response = client.get("/api/model-providers")

    assert response.status_code == 200, response.text
    providers = {item["provider"]: item for item in response.json()["providers"]}
    assert set(providers) == {
        "openai",
        "anthropic",
        "google_vertexai",
        "google_genai",
        "deepseek",
        "xai",
    }
    assert all(item["installed"] for item in providers.values())
    assert all(item["version"] for item in providers.values())
    assert "openrouter" not in providers
    assert not (tmp_path / "data" / "resources" / "provider_integrations").exists()


def test_runtime_has_no_user_provider_install_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    response = client.post("/api/model-providers/openrouter/install")

    assert response.status_code == 404


def test_bundled_provider_set_is_backed_by_current_langchain_registry() -> None:
    integrations = {item.provider: item for item in bundled_provider_integrations()}

    assert integrations["openai"].package == "langchain-openai"
    assert integrations["deepseek"].package == "langchain-deepseek"
    assert integrations["xai"].package == "langchain-xai"
