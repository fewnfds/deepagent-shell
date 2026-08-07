from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from agent_shell.readiness import ReadinessService


def build_system_router(
    readiness: ReadinessService,
    management_auth_enabled_provider: Callable[[], bool],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "runtime": "model_streaming",
            "management_auth_enabled": management_auth_enabled_provider(),
        }

    @router.get("/api/readiness")
    async def readiness_report() -> dict[str, object]:
        return readiness.snapshot()

    return router
