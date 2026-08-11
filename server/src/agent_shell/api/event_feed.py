from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from agent_shell.api.errors import management_error
from agent_shell.event_feed import (
    EventFeedService,
    EventLevel,
    EventSource,
)
from agent_shell.runtime.interception import InterceptionTestController
from agent_shell.storage.api_server import ApiServerStore
from agent_shell.storage.history_retention import MAX_HISTORY_RETENTION_LIMIT
from agent_shell.storage.system_log_settings import (
    MAX_SYSTEM_LOG_MAX_SIZE_MIB,
    MIN_SYSTEM_LOG_MAX_SIZE_MIB,
)


class InterceptionTestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class EventFeedDeleteMatching(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    ended_at: datetime
    source: list[EventSource] = Field(default_factory=list)
    level: list[EventLevel] = Field(default_factory=list)
    query: str = Field(default="", max_length=200)


class HistoryRetentionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_limit: int = Field(ge=1, le=MAX_HISTORY_RETENTION_LIMIT)


class SystemLogSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_size_mib: int = Field(
        ge=MIN_SYSTEM_LOG_MAX_SIZE_MIB,
        le=MAX_SYSTEM_LOG_MAX_SIZE_MIB,
    )


def _time_window(started_at: datetime, ended_at: datetime) -> tuple[datetime, datetime]:
    if (
        started_at.tzinfo is None
        or started_at.utcoffset() is None
        or ended_at.tzinfo is None
        or ended_at.utcoffset() is None
    ):
        raise management_error(
            422,
            code="event_feed_time_window_invalid",
            message_key="errors.eventFeedTimeWindowInvalid",
            message="The event feed time window must include a timezone.",
        )
    started_at = started_at.astimezone(timezone.utc)
    ended_at = ended_at.astimezone(timezone.utc)
    if ended_at < started_at:
        raise management_error(
            422,
            code="event_feed_time_window_invalid",
            message_key="errors.eventFeedTimeWindowInvalid",
            message="The event feed end time must not be earlier than the start time.",
        )
    return started_at, ended_at


def build_event_feed_router(
    service: EventFeedService,
    store: ApiServerStore,
    events: Any,
    interception_tests: InterceptionTestController,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/event-feed")
    async def list_event_feed(
        started_at: datetime = Query(),
        ended_at: datetime = Query(),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        source: list[EventSource] = Query(default=[]),
        level: list[EventLevel] = Query(default=[]),
        query: str = Query(default="", max_length=200),
    ) -> dict[str, object]:
        started_at, ended_at = _time_window(started_at, ended_at)
        return service.list_events(
            page=page,
            page_size=page_size,
            started_at=started_at,
            ended_at=ended_at,
            sources=set(source),
            levels=set(level),
            query=query.strip(),
        )

    @router.post("/api/event-feed/delete")
    async def delete_matching_events(
        payload: EventFeedDeleteMatching,
    ) -> dict[str, int]:
        started_at, ended_at = _time_window(payload.started_at, payload.ended_at)
        result = service.delete_matching(
            started_at=started_at,
            ended_at=ended_at,
            sources=set(payload.source),
            levels=set(payload.level),
            query=payload.query.strip(),
        )
        await events.publish({"type": "history_changed"})
        return result

    @router.get("/api/event-feed/{source}/{item_id}/download")
    async def download_event(
        source: EventSource,
        item_id: str,
    ) -> Response:
        result = service.download(source, item_id)
        if result is None:
            raise management_error(
                404,
                code="event_feed_item_not_found",
                message_key="errors.eventFeedItemNotFound",
                message="The event feed item does not exist.",
            )
        content, filename, media_type = result
        if isinstance(content, Path):
            return FileResponse(
                content,
                filename=filename,
                media_type=media_type,
            )
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.get("/api/event-feed/system/settings")
    async def get_system_log_settings() -> dict[str, int]:
        return service.system_log_settings()

    @router.put("/api/event-feed/system/settings")
    async def update_system_log_settings(
        payload: SystemLogSettingsUpdate,
    ) -> dict[str, int]:
        result = service.set_system_log_max_size_mib(payload.max_size_mib)
        await events.publish({"type": "settings_changed"})
        return result

    @router.get("/api/interception-test")
    async def get_interception_test() -> dict[str, bool]:
        return interception_tests.snapshot()

    @router.put("/api/interception-test")
    async def update_interception_test(
        payload: InterceptionTestUpdate,
    ) -> dict[str, bool]:
        state = interception_tests.set_enabled(payload.enabled)
        await events.publish({"type": "interception_changed"})
        return state

    @router.get("/api/interception-test/records/retention")
    async def get_interception_retention() -> dict[str, int]:
        return store.history_retention("interception_history")

    @router.put("/api/interception-test/records/retention")
    async def update_interception_retention(
        payload: HistoryRetentionUpdate,
    ) -> dict[str, int]:
        result = store.set_history_retention(
            "interception_history", payload.retention_limit
        )
        await events.publish({"type": "interception_changed"})
        return result

    return router
