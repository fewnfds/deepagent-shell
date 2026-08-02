from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from agent_shell.api.agent_configs import ConfigurationBulkDelete
from agent_shell.api.errors import management_error
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.validation.models import ValidationReport, validation_failure_detail
from agent_shell.validation.service import ConfigurationValidationService


WORKER_PROFILE_TABLE = "worker_profiles"


def _raise_if_invalid(report: ValidationReport) -> None:
    if not report.valid:
        raise HTTPException(status_code=422, detail=validation_failure_detail(report))


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


def _binding_owner(config_store: AgentConfigStore, profile_id: str) -> str:
    for owner in config_store.list_items("primary_agents"):
        workers = owner.get("workers", [])
        if not isinstance(workers, list):
            continue
        if any(
            isinstance(binding, dict)
            and binding.get("worker_profile_id") == profile_id
            for binding in workers
        ):
            return str(owner.get("name", ""))
    return ""


def _not_found() -> HTTPException:
    return management_error(
        404,
        code="worker_profile_not_found",
        message_key="errors.workerProfileNotFound",
        message="The Context Worker profile does not exist.",
    )


def _save(
    store: AgentConfigStore,
    item_id: str,
    validated: dict,
) -> dict:
    try:
        store.save_item(WORKER_PROFILE_TABLE, item_id, validated)
    except ValueError as exc:
        raise management_error(
            409,
            code="configuration_name_conflict",
            message_key="errors.configurationNameConflict",
            message="A configuration with this name already exists.",
        ) from exc
    item = store.get_item(WORKER_PROFILE_TABLE, item_id)
    assert item is not None
    return item


def build_worker_profile_router(
    store: AgentConfigStore,
    validation: ConfigurationValidationService,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/worker-profiles")
    async def list_worker_profiles() -> list[dict]:
        return store.list_items(WORKER_PROFILE_TABLE)

    @router.post("/api/worker-profiles")
    async def create_worker_profile(payload: dict) -> dict:
        report, validated = validation.validate_worker_profile(
            payload, stage="worker_profile_save"
        )
        _raise_if_invalid(report)
        assert validated is not None
        return _save(store, str(uuid4()), validated)

    @router.post("/api/worker-profiles/delete")
    async def delete_worker_profiles(
        payload: ConfigurationBulkDelete,
    ) -> dict[str, int]:
        ids = list(dict.fromkeys(payload.ids))
        for item_id in ids:
            if store.get_item(WORKER_PROFILE_TABLE, item_id) is None:
                raise _not_found()
            owner = _binding_owner(store, item_id)
            if owner:
                raise management_error(
                    409,
                    code="configuration_referenced",
                    message_key="errors.configurationReferencedByPrimary",
                    message="The configuration is still referenced by a Primary Agent.",
                    message_args={"owner": owner},
                )
        return {"deleted": store.delete_items(WORKER_PROFILE_TABLE, ids)}

    @router.get("/api/worker-profiles/{item_id}")
    async def get_worker_profile(item_id: str) -> dict:
        item = store.get_item(WORKER_PROFILE_TABLE, item_id)
        if item is None:
            raise _not_found()
        return item

    @router.post("/api/worker-profiles/{item_id}/copy")
    async def copy_worker_profile(item_id: str, payload: dict) -> dict:
        source = store.get_item(WORKER_PROFILE_TABLE, item_id)
        if source is None:
            raise _not_found()
        candidate = dict(source)
        candidate["name"] = _copy_name(payload)
        report, validated = validation.validate_worker_profile(
            candidate,
            stage="worker_profile_copy",
            stored=True,
        )
        _raise_if_invalid(report)
        assert validated is not None
        return _save(store, str(uuid4()), validated)

    @router.put("/api/worker-profiles/{item_id}")
    async def update_worker_profile(item_id: str, payload: dict) -> dict:
        if store.get_item(WORKER_PROFILE_TABLE, item_id) is None:
            raise _not_found()
        report, validated = validation.validate_worker_profile(
            payload,
            stage="worker_profile_save",
            owner_id=item_id,
        )
        _raise_if_invalid(report)
        assert validated is not None
        return _save(store, item_id, validated)

    @router.delete("/api/worker-profiles/{item_id}")
    async def delete_worker_profile(item_id: str) -> dict[str, bool]:
        if store.get_item(WORKER_PROFILE_TABLE, item_id) is None:
            raise _not_found()
        owner = _binding_owner(store, item_id)
        if owner:
            raise management_error(
                409,
                code="configuration_referenced",
                message_key="errors.configurationReferencedByPrimary",
                message="The configuration is still referenced by a Primary Agent.",
                message_args={"owner": owner},
            )
        store.delete_item(WORKER_PROFILE_TABLE, item_id)
        return {"ok": True}

    return router
