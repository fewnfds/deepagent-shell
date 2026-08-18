from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_shell.contracts import RequiredReference

WorkflowRole = Literal["parent", "child"]


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    workflow_role: WorkflowRole
    description: Annotated[str, Field(max_length=2_000)] = ""
    filesystem_id: RequiredReference
    workflow_event_output_id: RequiredReference | None = None
    recursion_limit: Annotated[int, Field(ge=1, le=100_000)] = 100
    execution_timeout_seconds: Annotated[int, Field(ge=1, le=86_400)] = 600
    max_concurrency: Annotated[int, Field(ge=1, le=256)] = 16
    enabled: bool = True
