from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.automation.contracts import WORKFLOW_MODELS
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.contracts import BLOCK_MODELS
from agent_shell.storage.validation_settings import (
    MAX_VALIDATION_DEBOUNCE_MS,
    MIN_VALIDATION_DEBOUNCE_MS,
    ConfigurationValidationSettingsStore,
)
from agent_shell.validation.service import ConfigurationValidationService


class DraftValidationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["block", "primary", "subagent", "automation"]
    type: str = ""
    id: str = Field(default="", max_length=120)


class DraftValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: DraftValidationTarget
    payload: dict[str, Any]


class ConfigurationValidationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debounce_ms: int = Field(
        ge=MIN_VALIDATION_DEBOUNCE_MS,
        le=MAX_VALIDATION_DEBOUNCE_MS,
    )


def build_validation_router(
    validation: ConfigurationValidationService,
    automation_validation: AutomationValidationService,
    settings: ConfigurationValidationSettingsStore,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/validation/repository")
    async def validate_repository() -> dict[str, object]:
        return validation.validate_repository().as_dict()

    @router.get("/api/validation/settings")
    async def get_validation_settings() -> dict[str, int]:
        return settings.snapshot()

    @router.put("/api/validation/settings")
    async def update_validation_settings(
        payload: ConfigurationValidationSettingsUpdate,
    ) -> dict[str, int]:
        return settings.update(payload.debounce_ms)

    @router.post("/api/validation/draft")
    async def validate_draft(request: DraftValidationRequest) -> dict[str, object]:
        target = request.target
        if target.kind == "block":
            if target.type not in BLOCK_MODELS:
                raise management_error(
                    422,
                    code="unknown_configuration_type",
                    message_key="errors.unknownConfigurationType",
                    message="The requested configuration type is not supported.",
                    message_args={"type": target.type},
                )
            report, _ = validation.validate_block(
                target.type,
                request.payload,
                stage="draft_validation",
                owner_id=target.id,
            )
        elif target.kind == "primary":
            report, _, _ = validation.validate_primary(
                request.payload,
                stage="draft_validation",
                owner_id=target.id,
            )
        elif target.kind == "subagent":
            report, _ = validation.validate_subagent(
                request.payload,
                stage="draft_validation",
                owner_id=target.id,
            )
        else:
            if target.type not in WORKFLOW_MODELS:
                raise management_error(
                    422,
                    code="unknown_configuration_type",
                    message_key="errors.unknownConfigurationType",
                    message="The requested configuration type is not supported.",
                    message_args={"type": target.type},
                )
            report, _ = automation_validation.validate_workflow(
                target.type,
                request.payload,
                stage="workflow_draft",
                owner_id=target.id,
                stored=bool(target.id),
            )
        return report.as_dict()

    return router
