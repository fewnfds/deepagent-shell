from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_shell.api.errors import management_error
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.validation import ValidationIssue, report_from_validation_error
from agent_shell.validation.models import ValidationReport, validation_failure_detail
from agent_shell.validation.service import ConfigurationValidationService
from agent_shell.workflow.catalog import (
    ConditionRouterNodeConfig,
    TaskDispatcherNodeConfig,
    node_catalog_payload,
)
from agent_shell.workflow.contracts import WorkflowGraphDocumentV1
from agent_shell.workflow.validation import (
    WORKFLOW_ADMISSION_STAGE,
    WORKFLOW_EXECUTABLE_STAGE,
    admit_workflow_document,
    validate_workflow_executable,
)
from agent_shell.workflow_contracts import WorkflowDefinition, WorkflowRole


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
    existing = store.get_item(item_id)
    validated["enabled"] = existing["enabled"] if existing is not None else False
    if blocks.get_block("filesystem", validated["filesystem_id"]) is None:
        raise management_error(
            422,
            code="workflow_filesystem_not_found",
            message_key="errors.workflowFilesystemNotFound",
            message="The selected Workflow filesystem does not exist.",
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


def _parse_graph(
    payload: object,
) -> tuple[ValidationReport, WorkflowGraphDocumentV1 | None]:
    try:
        document = WorkflowGraphDocumentV1.model_validate(payload)
    except ValidationError as exc:
        return (
            report_from_validation_error(
                exc,
                stage=WORKFLOW_ADMISSION_STAGE,
                scope="workflow",
                owner_type="graph",
            ),
            None,
        )
    return ValidationReport(stage=WORKFLOW_ADMISSION_STAGE), document


def _executable_report(
    document: WorkflowGraphDocumentV1,
    *,
    workflow: dict,
    blocks: BlockStore,
    configuration_validation: ConfigurationValidationService,
) -> ValidationReport:
    condition_routers: dict[str, object] = {}
    task_dispatchers: dict[str, object] = {}
    referenced_issues: list[ValidationIssue] = []
    component_reports: dict[tuple[str, str], ValidationReport] = {}

    def component_report(
        block_type: str,
        reference: str,
        stored: dict,
    ) -> ValidationReport:
        key = (block_type, reference)
        report = component_reports.get(key)
        if report is None:
            report = configuration_validation.validate_stored_block(
                block_type,
                stored,
                stage=WORKFLOW_EXECUTABLE_STAGE,
            )
            component_reports[key] = report
        return report

    def project_component_report(
        *,
        node_id: str,
        node_type: str,
        node_index: int,
        reference_field: str,
        report: ValidationReport,
    ) -> None:
        for issue in report.issues:
            referenced_issues.append(
                ValidationIssue(
                    code=issue.code,
                    scope="workflow",
                    owner_id=node_id,
                    owner_name=node_id,
                    owner_type=node_type,
                    path=(
                        f"definition.nodes[{node_index}].config.{reference_field}"
                    ),
                    message=issue.message,
                    message_key=issue.message_key,
                    message_args=issue.message_args,
                    severity=issue.severity,
                )
            )

    for node_index, node in enumerate(document.definition.nodes):
        if node.type == "condition-router":
            reference = ConditionRouterNodeConfig.model_validate(
                node.config
            ).condition_router_id
            stored = blocks.get_block_internal("condition-router", str(reference))
            if stored is not None:
                report = component_report(
                    "condition-router",
                    str(reference),
                    stored,
                )
                project_component_report(
                    node_id=node.id,
                    node_type=node.type,
                    node_index=node_index,
                    reference_field="condition_router_id",
                    report=report,
                )
                condition_routers[node.id] = stored
        elif node.type == "task-dispatcher":
            reference = TaskDispatcherNodeConfig.model_validate(
                node.config
            ).task_dispatcher_id
            stored = blocks.get_block_internal("task-dispatcher", str(reference))
            if stored is not None:
                report = component_report(
                    "task-dispatcher",
                    str(reference),
                    stored,
                )
                project_component_report(
                    node_id=node.id,
                    node_type=node.type,
                    node_index=node_index,
                    reference_field="task_dispatcher_id",
                    report=report,
                )
                task_dispatchers[node.id] = stored

    def validate_main_agent(main_agent_id: str) -> ValidationReport:
        report, _ = configuration_validation.resolve_main_agent(
            main_agent_id,
            workflow_filesystem_id=str(workflow["filesystem_id"]),
            stage=WORKFLOW_EXECUTABLE_STAGE,
        )
        return report

    executable = validate_workflow_executable(
        document,
        validate_main_agent=validate_main_agent,
        condition_routers=condition_routers,
        task_dispatchers=task_dispatchers,
        workflow_role=workflow["workflow_role"],
    )
    return ValidationReport(
        stage=WORKFLOW_EXECUTABLE_STAGE,
        issues=(*executable.issues, *referenced_issues),
    )


def build_workflow_router(
    store: WorkflowStore,
    blocks: BlockStore,
    configuration_validation: ConfigurationValidationService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflow-node-catalog")
    async def get_workflow_node_catalog() -> list[dict[str, object]]:
        return node_catalog_payload()

    @router.get("/api/workflows")
    async def list_workflows(workflow_role: WorkflowRole | None = None) -> list[dict]:
        return store.list_items(workflow_role=workflow_role)

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
        workflow = store.get_item(item_id)
        if workflow is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        admission, document = admit_workflow_document(
            payload,
            workflow_role=workflow["workflow_role"],
        )
        if document is None:
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(admission),
            )
        report = _executable_report(
            document,
            workflow=workflow,
            blocks=blocks,
            configuration_validation=configuration_validation,
        )
        if not report.valid:
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(report),
            )
        if not store.save_graph_and_enabled(item_id, document, enabled=True):
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return document.model_dump(mode="json")

    @router.put("/api/workflows/{item_id}/draft")
    async def update_workflow_draft(item_id: str, payload: dict) -> dict:
        if store.get_item(item_id) is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        report, document = _parse_graph(payload)
        if document is None:
            raise HTTPException(
                status_code=422,
                detail=validation_failure_detail(report),
            )
        if not store.save_graph_and_enabled(item_id, document, enabled=False):
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        return document.model_dump(mode="json")

    @router.post("/api/workflows/{item_id}/validate")
    async def validate_workflow(item_id: str, payload: dict) -> dict:
        workflow = store.get_item(item_id)
        if workflow is None:
            raise management_error(
                404,
                code="workflow_not_found",
                message_key="errors.workflowNotFound",
                message="The Workflow does not exist.",
            )
        admission, document = admit_workflow_document(
            payload,
            workflow_role=workflow["workflow_role"],
        )
        if document is None:
            return admission.as_dict()
        return _executable_report(
            document,
            workflow=workflow,
            blocks=blocks,
            configuration_validation=configuration_validation,
        ).as_dict()

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
