from __future__ import annotations

from typing import Literal, NoReturn

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_shell.api.errors import management_error
from agent_shell.system_settings import SystemSettingsError, SystemSettingsService


class ManagementPasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["preserve", "replace"]
    value: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "ManagementPasswordUpdate":
        if self.operation == "replace" and not self.value:
            raise ValueError("replace requires a value")
        if self.operation != "replace" and self.value is not None:
            raise ValueError("value is accepted only for replace")
        return self


class SystemSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str
    port: int
    allow_remote: bool
    langsmith_tracing_enabled: bool
    management_token: ManagementPasswordUpdate
    cors_origins: list[str] = Field(max_length=100)
    trusted_proxy_cidrs: list[str] = Field(max_length=100)


def _raise_settings_error(error: SystemSettingsError) -> NoReturn:
    raise management_error(
        error.status_code,
        code=error.code,
        message_key=error.message_key,
        message=str(error),
        message_args=error.message_args,
    ) from error


def _with_active_url(payload: dict, request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    return {**payload, "active_management_url": f"{base}/admin"}


def build_system_settings_router(settings: SystemSettingsService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/system/settings")
    async def get_system_settings(request: Request) -> dict:
        return _with_active_url(settings.get(), request)

    @router.put("/api/system/settings")
    async def update_system_settings(
        payload: SystemSettingsUpdate,
        request: Request,
    ) -> dict:
        try:
            result = settings.update(payload.model_dump())
        except SystemSettingsError as exc:
            _raise_settings_error(exc)
        return _with_active_url(result, request)

    return router
