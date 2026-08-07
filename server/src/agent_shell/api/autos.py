from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from agent_shell.api.errors import management_error
from agent_shell.auto.contracts import AutoDefinition
from agent_shell.storage.autos import AutoStore


def build_auto_router(store: AutoStore) -> APIRouter:
    router = APIRouter()

    def parse(payload: object) -> AutoDefinition:
        try:
            return AutoDefinition.model_validate(payload)
        except ValidationError as exc:
            issues = [
                {
                    "type": item.get("type", "value_error"),
                    "loc": list(item.get("loc", ())),
                    "msg": item.get("msg", "Invalid value."),
                }
                for item in exc.errors(include_url=False)
            ]
            raise HTTPException(
                status_code=422,
                detail={"code": "auto_contract_invalid", "issues": issues},
            ) from exc

    @router.get("/api/auto-roots")
    async def list_auto_roots() -> list[dict]:
        return store.list_items()

    @router.get("/api/auto-roots/{auto_id}")
    async def get_auto_root(auto_id: str) -> dict:
        item = store.get_item(auto_id)
        if item is None:
            raise management_error(404, code="auto_not_found", message_key="errors.autoNotFound", message="The Auto root does not exist.")
        return item

    @router.post("/api/auto-roots")
    async def create_auto_root(payload: dict) -> dict:
        try:
            return store.save_item(str(uuid4()), parse(payload), expected_revision=None)
        except ValueError as exc:
            if str(exc) == "auto_public_id_conflict":
                raise management_error(409, code=str(exc), message_key="errors.autoPublicIdConflict", message="The Auto public id is already in use.") from exc
            raise

    @router.put("/api/auto-roots/{auto_id}")
    async def update_auto_root(auto_id: str, payload: dict) -> dict:
        if store.get_item(auto_id) is None:
            raise management_error(404, code="auto_not_found", message_key="errors.autoNotFound", message="The Auto root does not exist.")
        revision = payload.pop("revision", None)
        if not isinstance(revision, int) or isinstance(revision, bool):
            raise management_error(422, code="auto_revision_required", message_key="errors.autoRevisionRequired", message="Updating an Auto root requires its current revision.")
        try:
            return store.save_item(auto_id, parse(payload), expected_revision=revision)
        except ValueError as exc:
            code = str(exc)
            if code in {"auto_revision_conflict", "auto_public_id_conflict"}:
                raise management_error(409, code=code, message_key=f"errors.{code}", message="The Auto root changed or conflicts with another root.") from exc
            raise

    @router.delete("/api/auto-roots/{auto_id}")
    async def delete_auto_root(auto_id: str) -> dict[str, bool]:
        if not store.delete_item(auto_id):
            raise management_error(404, code="auto_not_found", message_key="errors.autoNotFound", message="The Auto root does not exist.")
        return {"ok": True}

    @router.post("/api/auto-roots/{auto_id}/resolve")
    async def resolve_auto_root(auto_id: str, payload: dict) -> dict[str, str]:
        item = store.get_item(auto_id)
        if item is None:
            raise management_error(404, code="auto_not_found", message_key="errors.autoNotFound", message="The Auto root does not exist.")
        from agent_shell.auto.resolver import resolve_auto_source

        return await resolve_auto_source(
            str(item.get("source", "")),
            payload.get("messages"),
        )

    return router
