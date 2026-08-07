from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    request_id: str
    workflow_id: str
    invocation_id: str
    services: Any = None
