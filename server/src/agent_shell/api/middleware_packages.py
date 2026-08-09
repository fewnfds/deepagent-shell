from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from agent_shell.middleware_packages.packages import scan_middleware_packages


def build_middleware_package_router(packages_dir: Path, runtime_root: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/api/middlewares/custom")
    async def middleware_packages() -> dict[str, object]:
        return scan_middleware_packages(packages_dir, runtime_root=runtime_root)

    return router
