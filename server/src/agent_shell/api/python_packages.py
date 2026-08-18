from __future__ import annotations

from fastapi import APIRouter

from agent_shell.python_packages.authoring import PythonPackageAuthoringService


def build_python_package_router(
    authoring: PythonPackageAuthoringService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/python-package-templates/middleware")
    async def middleware_templates() -> dict[str, object]:
        return authoring.template_catalog("custom-middleware")

    @router.get("/api/python-package-templates/command")
    async def command_templates() -> dict[str, object]:
        return authoring.template_catalog("command")

    @router.get("/api/python-package-templates/task-dispatcher")
    async def task_dispatcher_templates() -> dict[str, object]:
        return authoring.template_catalog("task-dispatcher")

    return router
