from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from agent_shell.automation.scripts import scan_automation_scripts


def build_automation_router(scripts_dir: Path, runtime_root: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/api/automation/plugins")
    async def automation_plugins() -> dict[str, object]:
        return scan_automation_scripts(scripts_dir, runtime_root=runtime_root)

    return router
