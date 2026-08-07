from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from agent_shell.workflow.contracts import StrictWorkflowModel
from agent_shell.public_ids import default_public_id


class AutoDefinition(StrictWorkflowModel):
    public_id: Annotated[str, Field(min_length=7, max_length=120)]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    source: Annotated[str, Field(min_length=1, max_length=200_000)]
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def default_public_id_from_name(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value.get("public_id"):
            value = dict(value)
            value["public_id"] = default_public_id("auto", str(value.get("name", "")))
        return value

    @field_validator("public_id")
    @classmethod
    def validate_public_id(cls, value: str) -> str:
        if not re.fullmatch(r"^auto-[a-z]+(?:-[a-z]+)*$", value):
            raise ValueError("Auto public_id must start with auto-")
        return value
