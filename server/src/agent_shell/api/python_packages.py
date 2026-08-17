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

    @router.get("/api/python-package-templates/workflow-prepare")
    async def workflow_prepare_templates() -> dict[str, object]:
        return authoring.template_catalog("workflow-prepare")

    @router.get("/api/python-package-templates/condition-router")
    async def condition_router_templates() -> dict[str, object]:
        return authoring.template_catalog("condition-router")

    @router.get("/api/python-package-templates/task-dispatcher")
    async def task_dispatcher_templates() -> dict[str, object]:
        return authoring.template_catalog("task-dispatcher")

    return router
