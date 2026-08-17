from __future__ import annotations

from collections import Counter
import math

from fastapi import APIRouter, Query

from agent_shell.api.errors import management_error
from agent_shell.runtime.background_tasks import (
    ACTIVE_BACKGROUND_STATUSES,
    BackgroundTaskManager,
)
from agent_shell.runtime.workflow_debug import WorkflowDebugService
from agent_shell.runtime.workflow_lifecycle import WorkflowLifecycleService


def build_workflow_lifecycle_router(
    lifecycle_service: WorkflowLifecycleService,
    background_tasks: BackgroundTaskManager,
    workflow_debug: WorkflowDebugService,
) -> APIRouter:
    router = APIRouter()

    async def summary(record: dict[str, object]) -> dict[str, object]:
        lifecycle_id = str(record["lifecycle_id"])
        tasks = await background_tasks.list(lifecycle_id)
        task_counts = Counter(task.runtime_status for task in tasks)
        thread_ids = {str(record.get("parent_thread_id", ""))}
        thread_ids.update(task.child_thread_id for task in tasks)
        thread_ids.discard("")
        checkpoint_count = 0
        debug_run_count = 0
        for thread_id in thread_ids:
            if workflow_debug.store.get(thread_id) is not None:
                debug_run_count += 1
            checkpoint_count += await workflow_debug.checkpoint_count(thread_id)
        filesystem = await lifecycle_service.filesystem_summary(lifecycle_id)
        return {
            **record,
            "lifecycle_status": record.get("lifecycle_status", "active"),
            "task_count": len(tasks),
            "active_task_count": sum(
                task_counts.get(status, 0) for status in ACTIVE_BACKGROUND_STATUSES
            ),
            "task_status_counts": dict(sorted(task_counts.items())),
            "debug_run_count": debug_run_count,
            "checkpoint_count": checkpoint_count,
            "store_item_count": await lifecycle_service.store_item_count(
                lifecycle_id
            ),
            **filesystem,
        }

    @router.get("/api/workflow-lifecycles")
    async def list_workflow_lifecycles(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        query: str = Query(default="", max_length=200),
    ) -> dict[str, object]:
        records, total = await lifecycle_service.list_records_page(
            limit=page_size,
            offset=(page - 1) * page_size,
            query=query,
        )
        return {
            "items": [
                await summary(record)
                for record in records
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 1,
        }

    @router.get("/api/workflow-lifecycles/{lifecycle_id}")
    async def get_workflow_lifecycle(
        lifecycle_id: str,
    ) -> dict[str, object]:
        record = await lifecycle_service.record(lifecycle_id)
        if record is None:
            raise management_error(
                404,
                code="workflow_lifecycle_not_found",
                message_key="errors.workflowLifecycleNotFound",
                message="The Workflow lifecycle does not exist.",
            )
        return await summary(record)

    @router.delete("/api/workflow-lifecycles/{lifecycle_id}")
    async def delete_workflow_lifecycle(
        lifecycle_id: str,
        delete_dynamic_directories: bool = Query(default=False),
    ) -> dict[str, object]:
        async with lifecycle_service.exclusive_mutation(lifecycle_id):
            record = await lifecycle_service.record(lifecycle_id)
            if record is None:
                raise management_error(
                    404,
                    code="workflow_lifecycle_not_found",
                    message_key="errors.workflowLifecycleNotFound",
                    message="The Workflow lifecycle does not exist.",
                )
            tasks = await background_tasks.list_for_cleanup(lifecycle_id)
            if record.get("parent_status") == "running" or any(
                task.runtime_status in ACTIVE_BACKGROUND_STATUSES for task in tasks
            ):
                raise management_error(
                    409,
                    code="workflow_lifecycle_active",
                    message_key="errors.workflowLifecycleActive",
                    message="A Workflow lifecycle with an active run cannot be deleted.",
                )
            await lifecycle_service.mark_deleting(lifecycle_id)
            thread_ids = {str(record.get("parent_thread_id", ""))}
            thread_ids.update(task.child_thread_id for task in tasks)
            thread_ids.discard("")
            for thread_id in thread_ids:
                await workflow_debug.purge_thread(thread_id)
            await lifecycle_service.delete(
                lifecycle_id,
                delete_dynamic_directories=delete_dynamic_directories,
            )
        return {
            "ok": True,
            "deleted_thread_count": len(thread_ids),
            "deleted_dynamic_directories": delete_dynamic_directories,
        }

    return router


__all__ = ["build_workflow_lifecycle_router"]
