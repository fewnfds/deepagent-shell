from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.automation.contracts import WORKFLOW_MODELS
from agent_shell.automation.scripts import scan_automation_scripts
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.automation import AutomationStore
from agent_shell.validation.models import validation_failure_detail


class WorkflowBulkDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(max_length=10_000)


def _copy_name(payload: dict[str, Any]) -> str:
    if set(payload) != {"name"} or not isinstance(payload.get("name"), str):
        raise management_error(
            422,
            code="invalid_copy_request",
            message_key="errors.copyRequestInvalid",
            message="The copy request must contain only a configuration name.",
        )
    name = payload["name"].strip()
    if not name or len(name) > 120:
        raise management_error(
            422,
            code="invalid_configuration_name_length",
            message_key="errors.configurationNameLength",
            message="The configuration name must contain 1 to 120 characters.",
            message_args={"minimum": 1, "maximum": 120},
        )
    return name


def _agent_workflow_reference(
    agent_configs: AgentConfigStore,
    workflow_type: str,
    workflow_id: str,
    *,
    ignored_subagent_ids: frozenset[str] = frozenset(),
) -> tuple[str, str] | None:
    field = (
        "hook_workflow_id"
        if workflow_type == "hook-workflow"
        else "lifecycle_workflow_id"
    )
    selection_field = (
        "hook_workflow"
        if workflow_type == "hook-workflow"
        else "lifecycle_workflow"
    )
    for primary in agent_configs.list_items("primary_agents"):
        automation = primary.get("automation", {})
        if isinstance(automation, dict) and automation.get(field) == workflow_id:
            return "primary", str(primary.get("name", ""))
    for subagent in agent_configs.list_items("subagents"):
        if str(subagent.get("id", "")) in ignored_subagent_ids:
            continue
        settings = subagent.get("settings", {})
        automation = settings.get("automation", {}) if isinstance(settings, dict) else {}
        selection = (
            automation.get(selection_field, {}) if isinstance(automation, dict) else {}
        )
        if (
            isinstance(selection, dict)
            and selection.get("mode") == "replace"
            and selection.get("workflow_id") == workflow_id
        ):
            return "subagent", str(subagent.get("component_name", ""))
    return None


def build_automation_router(
    store: AutomationStore,
    agent_configs: AgentConfigStore,
    validation: AutomationValidationService,
    scripts_dir: Path,
) -> APIRouter:
    router = APIRouter()

    def check_type(workflow_type: str) -> None:
        if workflow_type not in WORKFLOW_MODELS:
            raise management_error(
                404,
                code="unknown_workflow_type",
                message_key="errors.unknownWorkflowType",
                message="The automation workflow type is unknown.",
                message_args={"type": workflow_type},
            )

    def validated_payload(
        workflow_type: str,
        payload: dict[str, Any],
        *,
        item_id: str = "",
        stored: bool = False,
    ) -> dict[str, Any]:
        report, validated = validation.validate_workflow(
            workflow_type,
            payload,
            stage="workflow_save",
            owner_id=item_id,
            stored=stored,
        )
        if not report.valid:
            raise HTTPException(status_code=422, detail=validation_failure_detail(report))
        assert validated is not None
        return validated

    @router.get("/api/automation/scripts")
    async def scripts() -> dict[str, object]:
        return scan_automation_scripts(scripts_dir)

    @router.get("/api/automation/{workflow_type}")
    async def list_workflows(workflow_type: str) -> list[dict]:
        check_type(workflow_type)
        return store.list_items(workflow_type)

    @router.post("/api/automation/{workflow_type}/validate")
    async def validate_workflow(
        workflow_type: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        check_type(workflow_type)
        report, _validated = validation.validate_workflow(
            workflow_type,
            payload,
            stage="workflow_draft",
            owner_id=str(payload.get("id", "")),
            stored=bool(payload.get("id")),
        )
        return report.as_dict()

    @router.get("/api/automation/{workflow_type}/{item_id}")
    async def get_workflow(workflow_type: str, item_id: str) -> dict:
        check_type(workflow_type)
        item = store.get_item(workflow_type, item_id)
        if item is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The automation workflow does not exist.",
            )
        return item

    @router.post("/api/automation/{workflow_type}")
    async def create_workflow(workflow_type: str, payload: dict[str, Any]) -> dict:
        check_type(workflow_type)
        validated = validated_payload(workflow_type, payload)
        item_id = str(uuid4())
        try:
            store.save_item(workflow_type, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        item = store.get_item(workflow_type, item_id)
        assert item is not None
        return item

    @router.put("/api/automation/{workflow_type}/{item_id}")
    async def update_workflow(
        workflow_type: str, item_id: str, payload: dict[str, Any]
    ) -> dict:
        check_type(workflow_type)
        if store.get_item(workflow_type, item_id) is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The automation workflow does not exist.",
            )
        validated = validated_payload(workflow_type, payload, item_id=item_id)
        try:
            store.save_item(workflow_type, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        item = store.get_item(workflow_type, item_id)
        assert item is not None
        return item

    @router.post("/api/automation/{workflow_type}/{item_id}/copy")
    async def copy_workflow(
        workflow_type: str, item_id: str, payload: dict[str, Any]
    ) -> dict:
        check_type(workflow_type)
        source = store.get_item(workflow_type, item_id)
        if source is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The automation workflow does not exist.",
            )
        candidate = dict(source)
        candidate["name"] = _copy_name(payload)
        validated = validated_payload(workflow_type, candidate, stored=True)
        copy_id = str(uuid4())
        try:
            store.save_item(workflow_type, copy_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        copied = store.get_item(workflow_type, copy_id)
        assert copied is not None
        return copied

    @router.delete("/api/automation/{workflow_type}/{item_id}")
    async def delete_workflow(workflow_type: str, item_id: str) -> dict[str, bool]:
        check_type(workflow_type)
        if store.get_item(workflow_type, item_id) is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The automation workflow does not exist.",
            )
        owner = _agent_workflow_reference(agent_configs, workflow_type, item_id)
        if owner is not None:
            owner_type, owner_name = owner
            raise management_error(
                409,
                code="configuration_referenced",
                message_key=(
                    "errors.configurationReferencedByPrimary"
                    if owner_type == "primary"
                    else "errors.configurationReferencedBySubagent"
                ),
                message="The workflow is still referenced by an Agent.",
                message_args={"owner": owner_name},
            )
        store.delete_item(workflow_type, item_id)
        return {"ok": True}

    @router.post("/api/automation/{workflow_type}/delete")
    async def delete_workflows(
        workflow_type: str, payload: WorkflowBulkDelete
    ) -> dict[str, int]:
        check_type(workflow_type)
        ids = list(dict.fromkeys(payload.ids))
        for item_id in ids:
            if store.get_item(workflow_type, item_id) is None:
                raise management_error(
                    404,
                    code="workflow_not_found",
                    message_key="errors.workflowNotFound",
                    message="An automation workflow does not exist.",
                )
            owner = _agent_workflow_reference(agent_configs, workflow_type, item_id)
            if owner is not None:
                owner_type, owner_name = owner
                raise management_error(
                    409,
                    code="configuration_referenced",
                    message_key=(
                        "errors.configurationReferencedByPrimary"
                        if owner_type == "primary"
                        else "errors.configurationReferencedBySubagent"
                    ),
                    message="The workflow is still referenced by an Agent.",
                    message_args={"owner": owner_name},
                )
        return {"deleted": store.delete_items(workflow_type, ids)}

    return router
