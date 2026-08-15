from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from agent_shell.condition_router_packages import scan_condition_router_packages
from agent_shell.middleware_packages.packages import scan_middleware_packages


def build_python_package_router(packages_dir: Path, runtime_root: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/api/python-packages/middleware/agent-middleware")
    async def middleware_packages() -> dict[str, object]:
        return scan_middleware_packages(packages_dir, runtime_root=runtime_root)

    @router.get("/api/python-packages/workflow-node/condition-router")
    async def condition_router_packages() -> dict[str, object]:
        return scan_condition_router_packages(packages_dir, runtime_root=runtime_root)

    return router
