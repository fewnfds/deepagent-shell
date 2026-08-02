from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.contracts import BLOCK_MODELS
from agent_shell.validation.service import ConfigurationValidationService


class DraftValidationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["block", "primary", "subagent-override", "worker-profile"]
    type: str = ""
    id: str = Field(default="", max_length=120)


class DraftValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: DraftValidationTarget
    payload: dict[str, Any]


def build_validation_router(
    validation: ConfigurationValidationService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/validation/repository")
    async def validate_repository() -> dict[str, object]:
        return validation.validate_repository().as_dict()

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
        elif target.kind == "subagent-override":
            report, _ = validation.validate_override(
                request.payload,
                stage="draft_validation",
                owner_id=target.id,
            )
        else:
            report, _ = validation.validate_worker_profile(
                request.payload,
                stage="draft_validation",
                owner_id=target.id,
            )
        return report.as_dict()

    return router
