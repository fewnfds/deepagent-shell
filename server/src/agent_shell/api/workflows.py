from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from agent_shell.api.errors import management_error
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.workflow.catalog import NodeRegistry, public_node_catalog
from agent_shell.workflow.validator import WorkflowValidator


def build_workflow_router(
    store: WorkflowStore,
    agents: AgentConfigStore,
    node_registry_provider: Callable[[], NodeRegistry] | None = None,
) -> APIRouter:
    router = APIRouter()

    def validator() -> WorkflowValidator:
        registry = node_registry_provider() if node_registry_provider is not None else NodeRegistry()
        return WorkflowValidator(workflow_lookup=store.get_item, agent_lookup=lambda agent_id: agents.get_item("main_agents", agent_id), node_registry=registry)

    def validated(payload: object, *, stage: str, owner_id: str = ""):
        report, definition = validator().validate_payload(payload, stage=stage, owner_id=owner_id)
        if not report.valid or definition is None:
            raise HTTPException(status_code=422, detail={"code": "workflow_validation_failed", "message": "The Graph definition is invalid.", "validation": report.as_dict()})
        return definition

    @router.get("/api/workflow-node-catalog")
    async def workflow_node_catalog() -> dict:
        registry = node_registry_provider() if node_registry_provider is not None else NodeRegistry()
        return public_node_catalog(registry)

    @router.get("/api/workflows")
    async def list_workflows() -> list[dict]:
        return store.list_items()

    @router.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict:
        item = store.get_item(workflow_id)
        if item is None:
            raise management_error(404, code="workflow_not_found", message_key="errors.workflowNotFound", message="The Graph does not exist.")
        return item

    @router.post("/api/workflows")
    async def create_workflow(payload: dict) -> dict:
        if "revision" in payload:
            raise management_error(422, code="workflow_revision_unexpected", message_key="errors.workflowRevisionUnexpected", message="A new Graph must not provide a revision.")
        definition = validated(payload, stage="workflow_create")
        return store.save_item(str(uuid4()), definition, expected_revision=None)

    @router.put("/api/workflows/{workflow_id}")
    async def update_workflow(workflow_id: str, payload: dict) -> dict:
        if store.get_item(workflow_id) is None:
            raise management_error(404, code="workflow_not_found", message_key="errors.workflowNotFound", message="The Graph does not exist.")
        revision = payload.pop("revision", None)
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise management_error(422, code="workflow_revision_required", message_key="errors.workflowRevisionRequired", message="Updating a Graph requires its current revision.")
        definition = validated(payload, stage="workflow_update", owner_id=workflow_id)
        try:
            return store.save_item(workflow_id, definition, expected_revision=revision)
        except ValueError as exc:
            if str(exc) == "workflow_revision_conflict":
                raise management_error(409, code=str(exc), message_key="errors.workflowRevisionConflict", message="The Graph changed elsewhere.") from exc
            raise

    @router.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str) -> dict[str, bool]:
        try:
            deleted = store.delete_item(workflow_id)
        except ValueError as exc:
            raise management_error(409, code=str(exc), message_key="errors.workflowReferenced", message="The Graph is still referenced by another Graph.") from exc
        if not deleted:
            raise management_error(404, code="workflow_not_found", message_key="errors.workflowNotFound", message="The Graph does not exist.")
        return {"ok": True}

    @router.post("/api/workflows/validate-draft")
    async def validate_workflow_draft(payload: dict) -> dict[str, object]:
        owner_id = str(payload.pop("id", ""))
        report, _ = validator().validate_payload(payload, stage="workflow_draft", owner_id=owner_id)
        return report.as_dict()

    return router
