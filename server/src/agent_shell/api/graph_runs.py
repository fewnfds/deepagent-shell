from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.graph_run_service import GraphRunService
from agent_shell.storage.workflows import WorkflowStore


def build_graph_run_router(service: GraphRunService, workflows: WorkflowStore) -> APIRouter:
    router = APIRouter()

    def error(exc: AgentRuntimeError) -> HTTPException:
        return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.safe_message})

    @router.get("/api/graph-runs")
    async def list_graph_runs(graph_id: str | None = None) -> list[dict]:
        return service.list_runs(graph_id)

    @router.get("/api/graph-runs/{run_id}")
    async def get_graph_run(run_id: str) -> dict:
        item = service.get_run(run_id)
        if item is None:
            raise HTTPException(status_code=404, detail={"code": "graph_run_not_found", "message": "The graph run does not exist."})
        return item

    @router.post("/api/workflows/{workflow_id}/runs")
    async def start_graph_run(workflow_id: str, payload: dict) -> dict:
        if workflows.get_item(workflow_id) is None:
            raise HTTPException(status_code=404, detail={"code": "workflow_not_found", "message": "The Graph does not exist."})
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            raise HTTPException(status_code=422, detail={"code": "messages_invalid", "message": "messages must be an array."})
        try:
            return await service.start(workflow_id, messages=messages, entry_script_id=payload.get("entry_script_id"), run_id=payload.get("run_id"), resume=bool(payload.get("resume", False)))
        except AgentRuntimeError as exc:
            raise error(exc) from exc

    @router.post("/api/graph-runs/{run_id}/pause")
    async def pause_graph_run(run_id: str) -> dict:
        try:
            return await service.pause(run_id)
        except AgentRuntimeError as exc:
            raise error(exc) from exc

    @router.post("/api/graph-runs/{run_id}/resume")
    async def resume_graph_run(run_id: str) -> dict:
        try:
            return await service.resume(run_id)
        except AgentRuntimeError as exc:
            raise error(exc) from exc

    @router.post("/api/graph-runs/{run_id}/cancel")
    async def cancel_graph_run(run_id: str) -> dict:
        try:
            return await service.cancel(run_id)
        except AgentRuntimeError as exc:
            raise error(exc) from exc

    @router.get("/api/graph-runs/{run_id}/events")
    async def graph_run_events(run_id: str) -> StreamingResponse:
        async def stream():
            try:
                async for event in service.stream(run_id):
                    yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            except AgentRuntimeError as exc:
                yield f"data: {json.dumps({'type': 'graph_run', 'run_id': run_id, 'event': 'failed', 'error_code': exc.code}, ensure_ascii=False)}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router
