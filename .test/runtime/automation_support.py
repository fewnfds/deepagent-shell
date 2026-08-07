from __future__ import annotations

import json
from pathlib import Path

from agent_shell.automation.runtime import AutomationOwner, AutomationRuntime


def write_plugin(
    root: Path,
    plugin_id: str,
    source: str,
    *,
    entrypoints: tuple[str, ...],
    config_schema: dict[str, object] | None = None,
) -> Path:
    folder = root / plugin_id
    folder.mkdir(parents=True)
    (folder / "script.json").write_text(
        json.dumps(
            {
                "api_version": 3,
                "id": plugin_id,
                "name": plugin_id,
                "description": "Test plugin",
                "entrypoints": list(entrypoints),
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                } if config_schema is None else config_schema,
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(source, encoding="utf-8")
    return folder


def owner(
    plugin_id: str,
    *,
    interval: float | None = None,
    config: dict[str, object] | None = None,
) -> AutomationOwner:
    binding = {
        "plugin_id": plugin_id,
        "enabled": True,
        "config": config or {},
    }
    return AutomationOwner(
        id="owner",
        type="main_agent",
        name="Main Agent",
        automation={
            "hooks": [binding] if interval is None else [],
            "periodic": (
                [{**binding, "interval_seconds": interval}]
                if interval is not None
                else []
            ),
        },
        mapped_paths={},
    )


def runtime_for(
    tmp_path: Path,
    plugin_id: str,
    *,
    interval: float | None = None,
    config: dict[str, object] | None = None,
) -> AutomationRuntime:
    return AutomationRuntime(
        request_id="request-id",
        owners=[owner(plugin_id, interval=interval, config=config)],
        client_messages=[{"role": "user", "content": "original"}],
        plugins_dir=tmp_path / "plugins",
        skills_dir=tmp_path / "skills",
        runtime_root=tmp_path / "runtime",
    )
