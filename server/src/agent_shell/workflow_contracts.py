from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=2_000)] = ""
    main_agent_id: Annotated[str, Field(min_length=1, max_length=120)]
    enabled: bool = True

