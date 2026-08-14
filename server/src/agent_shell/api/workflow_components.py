from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import ValidationError

from agent_shell.api.errors import management_error
from agent_shell.python_requirements import parse_python_requirements
from agent_shell.storage.workflow_components import WorkflowComponentStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.workflow_components import (
    WorkflowComponentDefinition,
    WorkflowComponentInstance,
    validate_workflow_component_config,
)


def build_workflow_component_router(
    store: WorkflowComponentStore,
    workflows: WorkflowStore,
) -> APIRouter:
    router = APIRouter()

    def parse_definition(payload: object) -> dict:
        try:
            definition = WorkflowComponentDefinition.model_validate(payload)
        except ValidationError as exc:
            raise management_error(
                422,
                code="workflow_component_definition_invalid",
                message_key="errors.workflowComponentDefinitionInvalid",
                message="The Workflow component definition is invalid.",
                message_args={"count": len(exc.errors())},
            ) from exc
        return definition.model_dump(mode="json")

    def definition_or_404(definition_id: str) -> dict:
        definition = store.get_definition(definition_id)
        if definition is None:
            raise management_error(
                404,
                code="workflow_component_definition_not_found",
                message_key="errors.workflowComponentDefinitionNotFound",
                message="The Workflow component definition does not exist.",
            )
        return definition

    def project_definition(definition: dict) -> dict:
        requirements = parse_python_requirements(
            definition.get("python_requirements", [])
        )
        return {
            **definition,
            "requirements_fingerprint": requirements.fingerprint,
        }

    def validate_existing_instances(definition_id: str, definition: dict) -> None:
        for instance in store.list_instances(definition_id=definition_id):
            issue = validate_workflow_component_config(
                definition["config_schema"], instance["config"]
            )
            if issue is None:
                continue
            raise management_error(
                409,
                code="workflow_component_definition_instances_invalid",
                message_key="errors.workflowComponentDefinitionInstancesInvalid",
                message=(
                    "The changed schema would invalidate an existing Workflow "
                    "component instance."
                ),
                message_args={"instance": instance["name"]},
            )

    def parse_instance(payload: object) -> dict:
        try:
            instance = WorkflowComponentInstance.model_validate(payload)
        except ValidationError as exc:
            raise management_error(
                422,
                code="workflow_component_instance_invalid",
                message_key="errors.workflowComponentInstanceInvalid",
                message="The Workflow component instance is invalid.",
                message_args={"count": len(exc.errors())},
            ) from exc
        data = instance.model_dump(mode="json")
        definition = definition_or_404(data["definition_id"])
        issue = validate_workflow_component_config(
            definition["config_schema"], data["config"]
        )
        if issue is not None:
            raise management_error(
                422,
                code="workflow_component_instance_config_invalid",
                message_key="errors.workflowComponentInstanceConfigInvalid",
                message="The Workflow component instance config does not match its schema.",
                message_args={
                    "path": ".".join(issue.path),
                    "keyword": issue.keyword,
                },
            )
        return data

    def instance_or_404(instance_id: str) -> dict:
        instance = store.get_instance(instance_id)
        if instance is None:
            raise management_error(
                404,
                code="workflow_component_instance_not_found",
                message_key="errors.workflowComponentInstanceNotFound",
                message="The Workflow component instance does not exist.",
            )
        return instance

    @router.get("/api/workflow-component-definitions")
    async def list_definitions() -> list[dict]:
        return [project_definition(item) for item in store.list_definitions()]

    @router.post("/api/workflow-component-definitions")
    async def create_definition(payload: dict) -> dict:
        data = parse_definition(payload)
        definition_id = str(uuid4())
        try:
            store.save_definition(definition_id, data)
        except ValueError as exc:
            raise management_error(
                409,
                code="workflow_component_definition_name_conflict",
                message_key="errors.workflowComponentDefinitionNameConflict",
                message="A Workflow component definition with this name already exists.",
            ) from exc
        return project_definition(definition_or_404(definition_id))

    @router.get("/api/workflow-component-definitions/{definition_id}")
    async def get_definition(definition_id: UUID) -> dict:
        return project_definition(definition_or_404(str(definition_id)))

    @router.put("/api/workflow-component-definitions/{definition_id}")
    async def update_definition(definition_id: UUID, payload: dict) -> dict:
        item_id = str(definition_id)
        definition_or_404(item_id)
        data = parse_definition(payload)
        validate_existing_instances(item_id, data)
        try:
            store.save_definition(item_id, data)
        except ValueError as exc:
            raise management_error(
                409,
                code="workflow_component_definition_name_conflict",
                message_key="errors.workflowComponentDefinitionNameConflict",
                message="A Workflow component definition with this name already exists.",
            ) from exc
        return project_definition(definition_or_404(item_id))

    @router.delete("/api/workflow-component-definitions/{definition_id}")
    async def delete_definition(definition_id: UUID) -> dict[str, bool]:
        item_id = str(definition_id)
        definition_or_404(item_id)
        instance = store.get_instance_by_definition(item_id)
        if instance is not None:
            raise management_error(
                409,
                code="workflow_component_definition_referenced",
                message_key="errors.workflowComponentDefinitionReferenced",
                message="The Workflow component definition still has instances.",
                message_args={"owner": instance["name"]},
            )
        store.delete_definition(item_id)
        return {"ok": True}

    @router.get("/api/workflow-component-instances")
    async def list_instances(definition_id: UUID | None = None) -> list[dict]:
        return store.list_instances(
            definition_id=str(definition_id) if definition_id is not None else None
        )

    @router.post("/api/workflow-component-instances")
    async def create_instance(payload: dict) -> dict:
        data = parse_instance(payload)
        instance_id = str(uuid4())
        try:
            store.save_instance(instance_id, data)
        except ValueError as exc:
            raise management_error(
                409,
                code="workflow_component_instance_name_conflict",
                message_key="errors.workflowComponentInstanceNameConflict",
                message=(
                    "A Workflow component instance with this name already exists "
                    "for the definition."
                ),
            ) from exc
        return instance_or_404(instance_id)

    @router.get("/api/workflow-component-instances/{instance_id}")
    async def get_instance(instance_id: UUID) -> dict:
        return instance_or_404(str(instance_id))

    @router.put("/api/workflow-component-instances/{instance_id}")
    async def update_instance(instance_id: UUID, payload: dict) -> dict:
        item_id = str(instance_id)
        instance_or_404(item_id)
        data = parse_instance(payload)
        try:
            store.save_instance(item_id, data)
        except ValueError as exc:
            raise management_error(
                409,
                code="workflow_component_instance_name_conflict",
                message_key="errors.workflowComponentInstanceNameConflict",
                message=(
                    "A Workflow component instance with this name already exists "
                    "for the definition."
                ),
            ) from exc
        return instance_or_404(item_id)

    @router.delete("/api/workflow-component-instances/{instance_id}")
    async def delete_instance(instance_id: UUID) -> dict[str, bool]:
        item_id = str(instance_id)
        instance_or_404(item_id)
        owner = workflows.get_item_by_component_instance(item_id)
        if owner is not None:
            raise management_error(
                409,
                code="workflow_component_instance_referenced",
                message_key="errors.workflowComponentInstanceReferenced",
                message="The Workflow component instance is still referenced.",
                message_args={"owner": owner["name"]},
            )
        store.delete_instance(item_id)
        return {"ok": True}

    return router


__all__ = ["build_workflow_component_router"]
