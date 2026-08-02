from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.validation.models import ValidationReport, validation_failure_detail
from agent_shell.validation.service import ConfigurationValidationService


PRIMARY_TABLE = "primary_agents"
OVERRIDE_TABLE = "subagent_overrides"


class ConfigurationBulkDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=1000)


def capability_reference_id(payload: dict, capability_type: str) -> str:
    references = payload.get("capability_refs", [])
    if not isinstance(references, list):
        return ""
    reference = next(
        (
            item
            for item in references
            if isinstance(item, dict) and item.get("type") == capability_type
        ),
        None,
    )
    return str(reference.get("block_id", "")) if reference else ""


def capability_override(payload: dict, capability_type: str) -> dict:
    overrides = payload.get("capability_overrides", [])
    if not isinstance(overrides, list):
        return {"type": capability_type, "mode": "inherit", "block_id": ""}
    return next(
        (
            item
            for item in overrides
            if isinstance(item, dict) and item.get("type") == capability_type
        ),
        {"type": capability_type, "mode": "inherit", "block_id": ""},
    )


def _raise_if_invalid(report: ValidationReport) -> None:
    if not report.valid:
        raise HTTPException(
            status_code=422,
            detail=validation_failure_detail(report),
        )


def _copy_name(payload: dict) -> str:
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

def block_reference_owner(
    config_store: AgentConfigStore, block_type: str, block_id: str
) -> tuple[str, str] | None:
    for item in config_store.list_items(PRIMARY_TABLE):
        if capability_reference_id(item, block_type) == block_id:
            return "primary", str(item.get("name", ""))

    for item in config_store.list_items(OVERRIDE_TABLE):
        selection = capability_override(item, block_type)
        if selection.get("mode") == "replace" and selection.get("block_id") == block_id:
            return "subagent_override", str(item.get("name", ""))
    for item in config_store.list_items("worker_profiles"):
        selection = capability_override(item, block_type)
        if selection.get("mode") == "replace" and selection.get("block_id") == block_id:
            return "worker_profile", str(item.get("name", ""))
    return None


def binding_reference_owner(
    config_store: AgentConfigStore,
    *,
    target_id: str,
) -> str:
    """Return the Primary owning a Subagent override reference, if any."""
    for owner in config_store.list_items(PRIMARY_TABLE):
        bindings = owner.get("subagents", [])
        if not isinstance(bindings, list):
            continue
        if any(
            isinstance(binding, dict)
            and binding.get("subagent_override_id") == target_id
            for binding in bindings
        ):
            return str(owner.get("name", ""))
    return ""


def build_agent_config_router(
    config_store: AgentConfigStore,
    validation: ConfigurationValidationService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/primary-agents")
    async def list_primary_agents() -> list[dict]:
        return config_store.list_items(PRIMARY_TABLE)

    @router.post("/api/primary-agents/delete")
    async def delete_primary_agents(
        payload: ConfigurationBulkDelete,
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(payload.ids))
        if any(config_store.get_item(PRIMARY_TABLE, item_id) is None for item_id in ids):
            raise management_error(
                404,
                code="primary_agent_not_found",
                message_key="errors.primaryAgentNotFound",
                message="A Primary Agent configuration does not exist.",
            )
        return {"deleted": config_store.delete_items(PRIMARY_TABLE, ids)}

    @router.get("/api/primary-agents/{item_id}")
    async def get_primary_agent(item_id: str) -> dict:
        item = config_store.get_item(PRIMARY_TABLE, item_id)
        if item is None:
            raise management_error(
                404,
                code="primary_agent_not_found",
                message_key="errors.primaryAgentNotFound",
                message="The Primary Agent configuration does not exist.",
            )
        return item

    @router.post("/api/primary-agents")
    async def create_primary_agent(payload: dict) -> dict:
        report, validated, _ = validation.validate_primary(
            payload,
            stage="primary_save",
        )
        _raise_if_invalid(report)
        assert validated is not None
        item_id = str(uuid4())
        try:
            config_store.save_item(PRIMARY_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(PRIMARY_TABLE, item_id)

    @router.post("/api/primary-agents/{item_id}/copy")
    async def copy_primary_agent(item_id: str, payload: dict) -> dict:
        name = _copy_name(payload)
        source = config_store.get_item(PRIMARY_TABLE, item_id)
        if source is None:
            raise management_error(
                404,
                code="primary_agent_not_found",
                message_key="errors.primaryAgentNotFound",
                message="The Primary Agent configuration does not exist.",
            )
        candidate = dict(source)
        candidate["name"] = name
        report, validated, _ = validation.validate_primary(
            candidate,
            stage="primary_copy",
            owner_id=item_id,
            stored=True,
        )
        _raise_if_invalid(report)
        assert validated is not None
        copy_id = str(uuid4())
        try:
            config_store.save_item(PRIMARY_TABLE, copy_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(PRIMARY_TABLE, copy_id)

    @router.put("/api/primary-agents/{item_id}")
    async def update_primary_agent(item_id: str, payload: dict) -> dict:
        if config_store.get_item(PRIMARY_TABLE, item_id) is None:
            raise management_error(
                404,
                code="primary_agent_not_found",
                message_key="errors.primaryAgentNotFound",
                message="The Primary Agent configuration does not exist.",
            )
        report, validated, _ = validation.validate_primary(
            payload,
            stage="primary_save",
            owner_id=item_id,
        )
        _raise_if_invalid(report)
        assert validated is not None
        try:
            config_store.save_item(PRIMARY_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(PRIMARY_TABLE, item_id)

    @router.delete("/api/primary-agents/{item_id}")
    async def delete_primary_agent(item_id: str) -> dict[str, bool]:
        if config_store.get_item(PRIMARY_TABLE, item_id) is None:
            raise management_error(
                404,
                code="primary_agent_not_found",
                message_key="errors.primaryAgentNotFound",
                message="The Primary Agent configuration does not exist.",
            )
        config_store.delete_item(PRIMARY_TABLE, item_id)
        return {"ok": True}

    @router.get("/api/subagent-overrides")
    async def list_subagent_overrides() -> list[dict]:
        return config_store.list_items(OVERRIDE_TABLE)

    @router.post("/api/subagent-overrides/delete")
    async def delete_subagent_overrides(
        payload: ConfigurationBulkDelete,
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(payload.ids))
        for item_id in ids:
            if config_store.get_item(OVERRIDE_TABLE, item_id) is None:
                raise management_error(
                    404,
                    code="subagent_override_not_found",
                    message_key="errors.subagentOverrideNotFound",
                    message="A Subagent override configuration does not exist.",
                )
            owner = binding_reference_owner(config_store, target_id=item_id)
            if owner:
                raise management_error(
                    409,
                    code="configuration_referenced",
                    message_key="errors.configurationReferencedByPrimary",
                    message="The configuration is still referenced by a Primary Agent.",
                    message_args={"owner": owner},
                )
        return {"deleted": config_store.delete_items(OVERRIDE_TABLE, ids)}

    @router.get("/api/subagent-overrides/{item_id}")
    async def get_subagent_override(item_id: str) -> dict:
        item = config_store.get_item(OVERRIDE_TABLE, item_id)
        if item is None:
            raise management_error(
                404,
                code="subagent_override_not_found",
                message_key="errors.subagentOverrideNotFound",
                message="The Subagent override configuration does not exist.",
            )
        return item

    @router.post("/api/subagent-overrides")
    async def create_subagent_override(payload: dict) -> dict:
        report, validated = validation.validate_override(
            payload,
            stage="subagent_override_save",
        )
        _raise_if_invalid(report)
        assert validated is not None
        item_id = str(uuid4())
        try:
            config_store.save_item(OVERRIDE_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(OVERRIDE_TABLE, item_id)

    @router.post("/api/subagent-overrides/{item_id}/copy")
    async def copy_subagent_override(item_id: str, payload: dict) -> dict:
        name = _copy_name(payload)
        source = config_store.get_item(OVERRIDE_TABLE, item_id)
        if source is None:
            raise management_error(
                404,
                code="subagent_override_not_found",
                message_key="errors.subagentOverrideNotFound",
                message="The Subagent override configuration does not exist.",
            )
        candidate = dict(source)
        candidate["name"] = name
        report, validated = validation.validate_override(
            candidate,
            stage="subagent_override_copy",
            stored=True,
        )
        _raise_if_invalid(report)
        assert validated is not None
        copy_id = str(uuid4())
        try:
            config_store.save_item(OVERRIDE_TABLE, copy_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(OVERRIDE_TABLE, copy_id)

    @router.put("/api/subagent-overrides/{item_id}")
    async def update_subagent_override(item_id: str, payload: dict) -> dict:
        if config_store.get_item(OVERRIDE_TABLE, item_id) is None:
            raise management_error(
                404,
                code="subagent_override_not_found",
                message_key="errors.subagentOverrideNotFound",
                message="The Subagent override configuration does not exist.",
            )
        report, validated = validation.validate_override(
            payload,
            stage="subagent_override_save",
            owner_id=item_id,
        )
        _raise_if_invalid(report)
        assert validated is not None
        try:
            config_store.save_item(OVERRIDE_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(OVERRIDE_TABLE, item_id)

    @router.delete("/api/subagent-overrides/{item_id}")
    async def delete_subagent_override(item_id: str) -> dict[str, bool]:
        if config_store.get_item(OVERRIDE_TABLE, item_id) is None:
            raise management_error(
                404,
                code="subagent_override_not_found",
                message_key="errors.subagentOverrideNotFound",
                message="The Subagent override configuration does not exist.",
            )
        owner = binding_reference_owner(
            config_store,
            target_id=item_id,
        )
        if owner:
            raise management_error(
                409,
                code="configuration_referenced",
                message_key="errors.configurationReferencedByPrimary",
                message="The configuration is still referenced by a Primary Agent.",
                message_args={"owner": owner},
            )
        config_store.delete_item(OVERRIDE_TABLE, item_id)
        return {"ok": True}

    return router
