from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_shell.api.errors import management_error
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.validation.models import validation_failure_detail
from agent_shell.workflow.catalog import node_catalog_payload
from agent_shell.workflow.validation import admit_workflow_document
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


def _save(
    store: WorkflowStore,
    blocks: BlockStore,
    item_id: str,
    payload: dict,
) -> dict:
    validated = _validated(payload)
    if blocks.get_block("filesystem", validated["filesystem_id"]) is None:
        raise management_error(
            422,
            code="workflow_filesystem_not_found",
            message_key="errors.workflowFilesystemNotFound",
            message="The selected Workflow filesystem does not exist.",
        )
    prepare_id = validated["workflow_prepare_id"]
    if prepare_id is not None and blocks.get_block("workflow-prepare", prepare_id) is None:
        raise management_error(
            422,
            code="workflow_prepare_not_found",
            message_key="errors.workflowPrepareNotFound",
            message="The selected Prepare component does not exist.",
        )
    event_output_id = validated["workflow_event_output_id"]
    if (
        event_output_id is not None
        and blocks.get_block("workflow-event-output", event_output_id) is None
    ):
        raise management_error(
            422,
            code="workflow_event_output_not_found",
            message_key="errors.workflowEventOutputNotFound",
            message="The selected event output component does not exist.",
        )
    try:
        store.save_item(item_id, validated)
    except ValueError as exc:
        raise management_error(
            409,
            code="workflow_name_conflict",
            message_key="errors.workflowNameConflict",
            message="A Workflow with this name already exists.",
        ) from exc
    item = store.get_item(item_id)
    assert item is not None
    return item


def build_workflow_router(
    store: WorkflowStore,
    blocks: BlockStore,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflow-node-catalog")
    async def get_workflow_node_catalog() -> list[dict[str, object]]:
        return node_catalog_payload()

    @router.get("/api/workflows")
    async def list_workflows() -> list[dict]:
        return store.list_items()

    @router.post("/api/workflows")
    async def create_workflow(payload: dict) -> dict:
        return _save(store, blocks, str(uuid4()), payload)

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
        return _save(store, blocks, item_id, payload)

    @router.get("/api/workflows/{item_id}/graph")
    async def get_workflow_graph(item_id: str) -> dict:
        document = store.get_graph(item_id)
        if document is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return document.model_dump(mode="json")

    @router.put("/api/workflows/{item_id}/graph")
    async def update_workflow_graph(item_id: str, payload: dict) -> dict:
        report, document = admit_workflow_document(payload)
        if document is None:
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(report),
            )
        if not store.save_graph(item_id, document):
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return document.model_dump(mode="json")

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
