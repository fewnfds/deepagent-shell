from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.storage.agent_sessions import AgentSessionStore
from agent_shell.storage.history_retention import MAX_HISTORY_RETENTION_LIMIT


class AgentSessionRetentionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_limit: int = Field(ge=1, le=MAX_HISTORY_RETENTION_LIMIT)


class AgentSessionDeleteMatching(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="", max_length=200)
    agent: str = Field(default="", max_length=200)
    status: str = Field(default="", max_length=40)


def build_agent_session_router(store: AgentSessionStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/agent-sessions")
    async def list_agent_sessions(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=10, le=100),
        query: str = Query(default="", max_length=200),
        agent: str = Query(default="", max_length=200),
        status: str = Query(default="", max_length=40),
    ) -> dict[str, object]:
        return store.list_sessions(
            page=page,
            page_size=page_size,
            query=query,
            agent=agent,
            status=status,
        )

    @router.get("/api/agent-sessions/retention")
    async def get_agent_session_retention() -> dict[str, int]:
        return store.history_retention()

    @router.put("/api/agent-sessions/retention")
    async def update_agent_session_retention(
        payload: AgentSessionRetentionUpdate,
    ) -> dict[str, int]:
        return store.set_history_retention(payload.retention_limit)

    @router.post("/api/agent-sessions/delete")
    async def delete_matching_agent_sessions(
        payload: AgentSessionDeleteMatching,
    ) -> dict[str, int]:
        return {
            "deleted": store.delete_matching_sessions(
                query=payload.query,
                agent=payload.agent,
                status=payload.status,
            )
        }

    @router.get("/api/agent-sessions/{session_id}")
    async def get_agent_session(session_id: str) -> dict[str, object]:
        item = store.get_session(session_id)
        if item is None:
            raise management_error(
                404,
                code="agent_session_not_found",
                message_key="errors.agentSessionNotFound",
                message="The Agent session record does not exist.",
            )
        return item

    @router.get("/api/agent-sessions/{session_id}/timeline")
    async def get_agent_session_timeline(session_id: str) -> dict[str, object]:
        item = store.get_session_timeline(session_id)
        if item is None:
            raise management_error(
                404,
                code="agent_session_not_found",
                message_key="errors.agentSessionNotFound",
                message="The Agent session record does not exist.",
            )
        return item

    @router.get(
        "/api/agent-sessions/{session_id}/runs/{run_id}/steps/{step_id}"
    )
    async def get_agent_session_step(
        session_id: str, run_id: str, step_id: str
    ) -> dict[str, object]:
        item = store.get_session_step(session_id, run_id, step_id)
        if item is None:
            raise management_error(
                404,
                code="agent_session_step_not_found",
                message_key="errors.agentSessionStepNotFound",
                message="The Agent session timeline step does not exist.",
            )
        return item

    @router.delete("/api/agent-sessions/{session_id}")
    async def delete_agent_session(session_id: str) -> dict[str, bool]:
        if not store.delete_session(session_id):
            raise management_error(
                404,
                code="agent_session_not_found",
                message_key="errors.agentSessionNotFound",
                message="The Agent session record does not exist.",
            )
        return {"deleted": True}

    return router
