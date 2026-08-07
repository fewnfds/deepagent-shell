from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import Field, field_validator

from agent_shell.workflow.contracts import StrictWorkflowModel


class AutoDefinition(StrictWorkflowModel):
    public_id: Annotated[str, Field(min_length=7, max_length=120)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    source: Annotated[str, Field(min_length=1, max_length=200_000)]
    enabled: bool = True

    @field_validator("public_id")
    @classmethod
    def validate_public_id(cls, value: str) -> str:
        if not re.fullmatch(r"^auto-[a-z]+(?:-[a-z]+)*$", value):
            raise ValueError("Auto public_id must start with auto-")
        return value
