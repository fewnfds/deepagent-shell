from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from agent_shell.contracts import RequiredReference


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=2_000)] = ""
    filesystem_id: RequiredReference
    enabled: bool = True
