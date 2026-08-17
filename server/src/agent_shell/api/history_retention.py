from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.storage.history_retention import MAX_HISTORY_RETENTION_LIMIT
from agent_shell.storage.workflow_runs import WorkflowRunStore


class WorkflowDebugRetentionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_limit: int = Field(ge=1, le=MAX_HISTORY_RETENTION_LIMIT)


def build_history_retention_router(workflow_runs: WorkflowRunStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/history-retention/workflow-debug")
    async def get_workflow_debug_retention() -> dict[str, int]:
        return workflow_runs.retention()

    @router.put("/api/history-retention/workflow-debug")
    async def update_workflow_debug_retention(
        payload: WorkflowDebugRetentionUpdate,
    ) -> dict[str, int]:
        return workflow_runs.set_retention(payload.retention_limit)

    return router


__all__ = ["build_history_retention_router"]
