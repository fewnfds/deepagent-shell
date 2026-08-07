from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from pydantic import ValidationError

from agent_shell.api.errors import management_error
from agent_shell.storage.entry_scripts import EntryScriptStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.workflow.contracts import EntryScriptDefinition


def build_entry_script_router(store: EntryScriptStore, workflows: WorkflowStore) -> APIRouter:
    router = APIRouter()

    def validate(payload: dict) -> EntryScriptDefinition:
        try:
            definition = EntryScriptDefinition.model_validate(payload)
        except ValidationError as exc:
            raise management_error(
                422,
                code="entry_script_validation_failed",
                message_key="errors.requestValidationFailed",
                message="The Entry Script definition is invalid.",
                message_args={"count": exc.error_count()},
            ) from exc
        graph = workflows.get_item(definition.graph_id)
        if graph is None:
            raise management_error(422, code="entry_script_graph_missing", message_key="errors.workflowNotFound", message="The selected Graph does not exist.")
        return definition

    @router.get("/api/entry-scripts")
    async def list_entry_scripts() -> list[dict]:
        return store.list_items()

    @router.get("/api/entry-scripts/{entry_script_id}")
    async def get_entry_script(entry_script_id: str) -> dict:
        result = store.get_item(entry_script_id)
        if result is None:
            raise management_error(404, code="entry_script_not_found", message_key="errors.requestFailed", message="The Entry Script does not exist.")
        return result

    @router.post("/api/entry-scripts")
    async def create_entry_script(payload: dict) -> dict:
        if "revision" in payload:
            raise management_error(422, code="entry_script_revision_unexpected", message_key="errors.requestValidationFailed", message="A new Entry Script must not include a revision.")
        try:
            definition = validate(payload)
            return store.save_item(str(uuid4()), definition, expected_revision=None)
        except ValueError as exc:
            if str(exc) == "entry_script_name_conflict":
                raise management_error(409, code=str(exc), message_key="errors.requestFailed", message="The Entry Script name is already in use.") from exc
            raise

    @router.put("/api/entry-scripts/{entry_script_id}")
    async def update_entry_script(entry_script_id: str, payload: dict) -> dict:
        current = store.get_item(entry_script_id)
        if current is None:
            raise management_error(404, code="entry_script_not_found", message_key="errors.requestFailed", message="The Entry Script does not exist.")
        revision = payload.pop("revision", None)
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise management_error(422, code="entry_script_revision_required", message_key="errors.requestValidationFailed", message="The current revision is required.")
        try:
            return store.save_item(entry_script_id, validate(payload), expected_revision=revision)
        except ValueError as exc:
            raise management_error(409, code=str(exc), message_key="errors.requestFailed", message="The Entry Script changed or its name is already in use.") from exc

    @router.delete("/api/entry-scripts/{entry_script_id}")
    async def delete_entry_script(entry_script_id: str) -> dict[str, bool]:
        if not store.delete_item(entry_script_id):
            raise management_error(404, code="entry_script_not_found", message_key="errors.requestFailed", message="The Entry Script does not exist.")
        return {"ok": True}

    return router
