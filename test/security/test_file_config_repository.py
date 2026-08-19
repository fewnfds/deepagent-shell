from __future__ import annotations

from pathlib import Path

import pytest

from agent_shell.storage import file_config
from agent_shell.storage.file_config import FileConfigRepository


def test_failed_config_write_keeps_live_and_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FileConfigRepository(tmp_path / "data")
    repository.update_config(
        lambda config: config["main_agents"].append(
            {"id": "agent-id", "name": "Original"}
        )
    )
    original_write = file_config._write_atomic

    def fail_candidate(path: Path, text: str) -> None:
        if path.name == "agent-id.yaml" and "Changed" in text:
            raise OSError("candidate write failed")
        original_write(path, text)

    monkeypatch.setattr(file_config, "_write_atomic", fail_candidate)

    with pytest.raises(OSError, match="candidate write failed"):
        repository.update_config(
            lambda config: config["main_agents"][0].__setitem__(
                "name", "Changed"
            )
        )

    assert repository.config()["main_agents"][0]["name"] == "Original"
    assert FileConfigRepository(tmp_path / "data").config()["main_agents"][0][
        "name"
    ] == "Original"


def test_failed_system_commit_restores_staged_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FileConfigRepository(tmp_path / "data")
    repository.set_secret("AGENT_SHELL_MANAGEMENT_TOKEN", "old-secret")
    original_write = file_config._write_atomic
    failed = False

    def fail_system_once(path: Path, text: str) -> None:
        nonlocal failed
        if path == repository.system_path and not failed:
            failed = True
            raise OSError("system write failed")
        original_write(path, text)

    monkeypatch.setattr(file_config, "_write_atomic", fail_system_once)

    def mutate(system: dict, environment: dict[str, str]) -> None:
        system["settings"] = {"port": 9123}
        environment["AGENT_SHELL_MANAGEMENT_TOKEN"] = "new-secret"

    with pytest.raises(OSError, match="system write failed"):
        repository.update_system_and_environment(mutate)

    assert repository.secret("AGENT_SHELL_MANAGEMENT_TOKEN") == "old-secret"
    reloaded = FileConfigRepository(tmp_path / "data")
    assert reloaded.secret("AGENT_SHELL_MANAGEMENT_TOKEN") == "old-secret"
    assert reloaded.system()["settings"].get("port") != 9123


def test_failed_component_commit_restores_staged_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FileConfigRepository(tmp_path / "data")
    original_write = file_config._write_atomic

    def fail_model(path: Path, text: str) -> None:
        if path.name == "model-id.yaml":
            raise OSError("model write failed")
        original_write(path, text)

    monkeypatch.setattr(file_config, "_write_atomic", fail_model)

    def mutate(config: dict, environment: dict[str, str]) -> None:
        config["components"].setdefault("model", []).append(
            {
                "id": "model-id",
                "name": "Model",
                "credential": {"reference": "MODEL_SECRET"},
            }
        )
        environment["MODEL_SECRET"] = "new-secret"

    with pytest.raises(OSError, match="model write failed"):
        repository.update_config_and_environment(mutate)

    assert repository.config()["components"].get("model") is None
    assert repository.secret("MODEL_SECRET") is None
    reloaded = FileConfigRepository(tmp_path / "data")
    assert reloaded.config()["components"].get("model", []) == []
    assert reloaded.secret("MODEL_SECRET") is None
