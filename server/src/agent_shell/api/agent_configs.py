from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.validation.models import ValidationReport, validation_failure_detail
from agent_shell.validation.service import ConfigurationValidationService


PRIMARY_TABLE = "primary_agents"
SUBAGENT_TABLE = "subagents"


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
    settings = payload.get("settings", {})
    overrides = (
        settings.get("capability_overrides", [])
        if isinstance(settings, dict)
        else []
    )
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


def _copy_component_name(payload: dict) -> str:
    if set(payload) != {"component_name"} or not isinstance(
        payload.get("component_name"), str
    ):
        raise management_error(
            422,
            code="invalid_copy_request",
            message_key="errors.copyRequestInvalid",
            message="The copy request must contain only a component name.",
        )
    component_name = payload["component_name"].strip()
    if not component_name or len(component_name) > 120:
        raise management_error(
            422,
            code="invalid_configuration_name_length",
            message_key="errors.configurationNameLength",
            message="The component name must contain 1 to 120 characters.",
            message_args={"minimum": 1, "maximum": 120},
        )
    return component_name

def block_reference_owner(
    config_store: AgentConfigStore, block_type: str, block_id: str
) -> tuple[str, str] | None:
    for item in config_store.list_items(PRIMARY_TABLE):
        if capability_reference_id(item, block_type) == block_id:
            return "primary", str(item.get("name", ""))

    for item in config_store.list_items(SUBAGENT_TABLE):
        selection = capability_override(item, block_type)
        if selection.get("mode") == "replace" and selection.get("block_id") == block_id:
            return "subagent", str(item.get("component_name", ""))
    return None


def subagent_reference_owner(
    config_store: AgentConfigStore,
    *,
    target_id: str,
    ignored_subagent_ids: frozenset[str] = frozenset(),
) -> tuple[str, str] | None:
    """Return a configuration that keeps a Subagent entity alive, if any."""
    for owner in config_store.list_items(PRIMARY_TABLE):
        references = owner.get("subagents", [])
        if not isinstance(references, list):
            continue
        if any(
            isinstance(reference, dict)
            and reference.get("subagent_id") == target_id
            for reference in references
        ):
            return "primary", str(owner.get("name", ""))

    for owner in config_store.list_items(SUBAGENT_TABLE):
        owner_id = str(owner.get("id", ""))
        if owner_id in ignored_subagent_ids:
            continue
        settings = owner.get("settings", {})
        references = settings.get("subagents", []) if isinstance(settings, dict) else []
        if not isinstance(references, list):
            continue
        if any(
            isinstance(reference, dict)
            and reference.get("subagent_id") == target_id
            for reference in references
        ):
            return "subagent", str(owner.get("component_name", ""))
    return None


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

    @router.get("/api/subagents")
    async def list_subagents() -> list[dict]:
        return config_store.list_items(SUBAGENT_TABLE)

    @router.post("/api/subagents/delete")
    async def delete_subagents(
        payload: ConfigurationBulkDelete,
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(payload.ids))
        deleting_ids = frozenset(ids)
        for item_id in ids:
            if config_store.get_item(SUBAGENT_TABLE, item_id) is None:
                raise management_error(
                    404,
                    code="subagent_not_found",
                    message_key="errors.subagentNotFound",
                    message="A Subagent entity does not exist.",
                )
            owner = subagent_reference_owner(
                config_store,
                target_id=item_id,
                ignored_subagent_ids=deleting_ids,
            )
            if owner:
                owner_type, owner_name = owner
                raise management_error(
                    409,
                    code="configuration_referenced",
                    message_key=(
                        "errors.configurationReferencedByPrimary"
                        if owner_type == "primary"
                        else "errors.configurationReferencedBySubagent"
                    ),
                    message=(
                        "The configuration is still referenced by a Primary Agent."
                        if owner_type == "primary"
                        else "The Subagent is still referenced by another Subagent."
                    ),
                    message_args={"owner": owner_name},
                )
        return {"deleted": config_store.delete_items(SUBAGENT_TABLE, ids)}

    @router.get("/api/subagents/{item_id}")
    async def get_subagent(item_id: str) -> dict:
        item = config_store.get_item(SUBAGENT_TABLE, item_id)
        if item is None:
            raise management_error(
                404,
                code="subagent_not_found",
                message_key="errors.subagentNotFound",
                message="The Subagent entity does not exist.",
            )
        return item

    @router.post("/api/subagents")
    async def create_subagent(payload: dict) -> dict:
        report, validated = validation.validate_subagent(
            payload,
            stage="subagent_save",
        )
        _raise_if_invalid(report)
        assert validated is not None
        item_id = str(uuid4())
        try:
            config_store.save_item(SUBAGENT_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(SUBAGENT_TABLE, item_id)

    @router.post("/api/subagents/{item_id}/copy")
    async def copy_subagent(item_id: str, payload: dict) -> dict:
        component_name = _copy_component_name(payload)
        source = config_store.get_item(SUBAGENT_TABLE, item_id)
        if source is None:
            raise management_error(
                404,
                code="subagent_not_found",
                message_key="errors.subagentNotFound",
                message="The Subagent entity does not exist.",
            )
        candidate = dict(source)
        candidate["component_name"] = component_name
        report, validated = validation.validate_subagent(
            candidate,
            stage="subagent_copy",
            stored=True,
        )
        _raise_if_invalid(report)
        assert validated is not None
        copy_id = str(uuid4())
        try:
            config_store.save_item(SUBAGENT_TABLE, copy_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(SUBAGENT_TABLE, copy_id)

    @router.put("/api/subagents/{item_id}")
    async def update_subagent(item_id: str, payload: dict) -> dict:
        if config_store.get_item(SUBAGENT_TABLE, item_id) is None:
            raise management_error(
                404,
                code="subagent_not_found",
                message_key="errors.subagentNotFound",
                message="The Subagent entity does not exist.",
            )
        report, validated = validation.validate_subagent(
            payload,
            stage="subagent_save",
            owner_id=item_id,
        )
        _raise_if_invalid(report)
        assert validated is not None
        try:
            config_store.save_item(SUBAGENT_TABLE, item_id, validated)
        except ValueError as exc:
            raise management_error(
                409,
                code="configuration_name_conflict",
                message_key="errors.configurationNameConflict",
                message="A configuration with this name already exists.",
            ) from exc
        return config_store.get_item(SUBAGENT_TABLE, item_id)

    @router.delete("/api/subagents/{item_id}")
    async def delete_subagent(item_id: str) -> dict[str, bool]:
        if config_store.get_item(SUBAGENT_TABLE, item_id) is None:
            raise management_error(
                404,
                code="subagent_not_found",
                message_key="errors.subagentNotFound",
                message="The Subagent entity does not exist.",
            )
        owner = subagent_reference_owner(
            config_store,
            target_id=item_id,
            ignored_subagent_ids=frozenset({item_id}),
        )
        if owner:
            owner_type, owner_name = owner
            raise management_error(
                409,
                code="configuration_referenced",
                message_key=(
                    "errors.configurationReferencedByPrimary"
                    if owner_type == "primary"
                    else "errors.configurationReferencedBySubagent"
                ),
                message=(
                    "The configuration is still referenced by a Primary Agent."
                    if owner_type == "primary"
                    else "The Subagent is still referenced by another Subagent."
                ),
                message_args={"owner": owner_name},
            )
        config_store.delete_item(SUBAGENT_TABLE, item_id)
        return {"ok": True}

    return router
