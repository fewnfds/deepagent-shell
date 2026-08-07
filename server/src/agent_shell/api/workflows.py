from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from agent_shell.api.errors import management_error
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.validation.models import validation_failure_detail
from agent_shell.workflow.catalog import public_node_catalog
from agent_shell.workflow.validator import WorkflowValidator


def build_workflow_router(store: WorkflowStore, agents: AgentConfigStore) -> APIRouter:
    router = APIRouter()

    def validator() -> WorkflowValidator:
        return WorkflowValidator(
            workflow_lookup=lambda workflow_id: store.get_item(workflow_id),
            agent_lookup=lambda agent_id: agents.get_item("main_agents", agent_id),
        )

    def validated(payload: object, *, stage: str, owner_id: str = ""):
        report, definition = validator().validate_payload(
            payload,
            stage=stage,
            owner_id=owner_id,
        )
        if not report.valid or definition is None:
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(report),
            )
        return definition

    @router.get("/api/workflow-node-catalog")
    async def workflow_node_catalog() -> dict:
        return public_node_catalog()

    @router.get("/api/workflows")
    async def list_workflows() -> list[dict]:
        return store.list_items()

    @router.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict:
        item = store.get_item(workflow_id)
        if item is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return item

    @router.post("/api/workflows")
    async def create_workflow(payload: dict) -> dict:
        if "revision" in payload:
            raise management_error(
                422,
                code="workflow_revision_unexpected",
                message_key="errors.workflowRevisionUnexpected",
                message="A new Workflow must not provide a revision.",
            )
        definition = validated(payload, stage="workflow_create")
        try:
            return store.save_item(
                str(uuid4()),
                definition,
                expected_revision=None,
            )
        except ValueError as exc:
            if str(exc) == "workflow_public_id_conflict":
                raise management_error(
                    409,
                    code="workflow_public_id_conflict",
                    message_key="errors.workflowPublicIdConflict",
                    message="The Workflow public id is already in use.",
                ) from exc
            raise

    @router.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, payload: dict) -> dict:
        existing = store.get_item(workflow_id)
        if existing is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        revision = payload.pop("revision", None)
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise management_error(
                422,
                code="workflow_revision_required",
                message_key="errors.workflowRevisionRequired",
                message="Updating a Workflow requires its current revision.",
            )
        definition = validated(
            payload,
            stage="workflow_update",
            owner_id=workflow_id,
        )
        try:
            return store.save_item(
                workflow_id,
                definition,
                expected_revision=revision,
            )
        except ValueError as exc:
            code = str(exc)
            if code == "workflow_revision_conflict":
                raise management_error(
                    409,
                    code=code,
                    message_key="errors.workflowRevisionConflict",
                    message="The Workflow changed after it was loaded.",
                ) from exc
            if code == "workflow_public_id_conflict":
                raise management_error(
                    409,
                    code=code,
                    message_key="errors.workflowPublicIdConflict",
                    message="The Workflow public id is already in use.",
                ) from exc
            raise

    @router.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str) -> dict[str, bool]:
        try:
            deleted = store.delete_item(workflow_id)
        except ValueError as exc:
            if str(exc) == "workflow_referenced":
                raise management_error(
                    409,
                    code="workflow_referenced",
                    message_key="errors.workflowReferenced",
                    message="The Workflow is still referenced by another Workflow.",
                ) from exc
            raise
        if not deleted:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return {"ok": True}

    @router.post("/api/workflows/validate-draft")
    async def validate_workflow_draft(payload: dict) -> dict[str, object]:
        owner_id = str(payload.pop("id", ""))
        report, _definition = validator().validate_payload(
            payload,
            stage="workflow_draft",
            owner_id=owner_id,
        )
        return report.as_dict()

    return router
