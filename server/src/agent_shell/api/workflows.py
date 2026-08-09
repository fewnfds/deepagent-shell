from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_shell.api.errors import management_error
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.workflow_contracts import WorkflowDefinition


class WorkflowBulkDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=1000)


def _validated(payload: dict) -> dict:
    try:
        return WorkflowDefinition.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise management_error(
            422,
            code="workflow_invalid",
            message_key="errors.workflowInvalid",
            message="The Workflow configuration is invalid.",
            message_args={"count": len(exc.errors())},
        ) from exc


def _save(store: WorkflowStore, item_id: str, payload: dict) -> dict:
    try:
        store.save_item(item_id, _validated(payload))
    except ValueError as exc:
        raise management_error(
            409,
            code="workflow_name_conflict",
            message_key="errors.workflowNameConflict",
            message="A Workflow with this name already exists.",
        ) from exc
    except LookupError as exc:
        raise management_error(
            422,
            code="workflow_main_agent_not_found",
            message_key="errors.workflowMainAgentNotFound",
            message="The selected Main Agent does not exist.",
        ) from exc
    item = store.get_item(item_id)
    assert item is not None
    return item


def build_workflow_router(store: WorkflowStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflows")
    async def list_workflows() -> list[dict]:
        return store.list_items()

    @router.post("/api/workflows")
    async def create_workflow(payload: dict) -> dict:
        return _save(store, str(uuid4()), payload)

    @router.post("/api/workflows/delete")
    async def delete_workflows(payload: WorkflowBulkDelete) -> dict[str, int]:
        ids = list(dict.fromkeys(payload.ids))
        if any(store.get_item(item_id) is None for item_id in ids):
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="A Workflow does not exist.",
            )
        return {"deleted": store.delete_items(ids)}

    @router.get("/api/workflows/{item_id}")
    async def get_workflow(item_id: str) -> dict:
        item = store.get_item(item_id)
        if item is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return item

    @router.put("/api/workflows/{item_id}")
    async def update_workflow(item_id: str, payload: dict) -> dict:
        if store.get_item(item_id) is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return _save(store, item_id, payload)

    @router.delete("/api/workflows/{item_id}")
    async def delete_workflow(item_id: str) -> dict[str, bool]:
        if not store.delete_item(item_id):
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return {"ok": True}

    return router

