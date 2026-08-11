from __future__ import annotations

from fastapi import APIRouter, Query

from agent_shell.api.errors import management_error
from agent_shell.runtime.workflow_debug import WorkflowDebugService


def build_workflow_debug_router(service: WorkflowDebugService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflow-debug/runs")
    async def list_workflow_debug_runs(
        limit: int = Query(default=50, ge=1, le=1000),
    ) -> dict[str, object]:
        return {"items": service.store.list(limit=limit)}

    @router.get("/api/workflow-debug/runs/{thread_id}")
    async def get_workflow_debug_run(thread_id: str) -> dict[str, object]:
        result = await service.detail(thread_id)
        if result is None:
            raise management_error(
                404,
                code="workflow_debug_run_not_found",
                message_key="errors.workflowDebugRunNotFound",
                message="The Workflow Debug run does not exist.",
            )
        return result

    @router.delete("/api/workflow-debug/runs/{thread_id}")
    async def delete_workflow_debug_run(thread_id: str) -> dict[str, bool]:
        current = service.store.get(thread_id)
        if current is not None and current["status"] == "running":
            raise management_error(
                409,
                code="workflow_debug_run_active",
                message_key="errors.workflowDebugRunActive",
                message="A running Workflow Debug run cannot be deleted.",
            )
        if not await service.delete(thread_id):
            raise management_error(
                404,
                code="workflow_debug_run_not_found",
                message_key="errors.workflowDebugRunNotFound",
                message="The Workflow Debug run does not exist.",
            )
        return {"ok": True}

    return router


__all__ = ["build_workflow_debug_router"]
