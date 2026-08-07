from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class GraphRunControl:
    """Cooperative run control used at node boundaries.

    LangGraph remains the scheduler.  This gate only lets the management UI
    pause/cancel a run between official node invocations.
    """

    paused: bool = False
    cancelled: bool = False
    _wake: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self._wake.set()

    async def check(self, _node_id: str = "") -> None:
        if self.cancelled:
            raise asyncio.CancelledError()
        await self._wake.wait()
        if self.cancelled:
            raise asyncio.CancelledError()

    def pause(self) -> None:
        self.paused = True
        self._wake.clear()

    def resume(self) -> None:
        self.paused = False
        self._wake.set()

    def cancel(self) -> None:
        self.cancelled = True
        self._wake.set()


@dataclass(frozen=True, slots=True)
class WorkflowContext(Mapping[str, Any]):
    request_id: str
    workflow_id: str
    invocation_id: str
    services: Any = None
    control: GraphRunControl | None = None
    emit: Any = None
    agent_contexts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        if key == "agent_contexts":
            return self.agent_contexts
        if key == "workflow_context":
            return self
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(("agent_contexts", "workflow_context"))

    def __len__(self) -> int:
        return 2
