from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agent_shell.python_requirements import parse_python_requirements
from agent_shell.script_source import validate_module_function


ScriptSource = Annotated[str, StringConstraints(strip_whitespace=False)]
DEFAULT_SESSION_TRANSFORM_SOURCE = (
    "def transform(messages, read_file, config, state, context):\n"
    "    return messages\n"
)


class SessionRecorderBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    enabled: bool = True
    custom_transform_enabled: bool = False
    custom_transform_source: ScriptSource = Field(
        default=DEFAULT_SESSION_TRANSFORM_SOURCE,
        max_length=100_000,
    )
    python_requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("python_requirements")
    @classmethod
    def validate_python_requirements(cls, values: list[str]) -> list[str]:
        return list(parse_python_requirements(values).values)

    @model_validator(mode="after")
    def validate_source(self) -> "SessionRecorderBlock":
        validate_module_function(
            self.custom_transform_source,
            "transform",
            asynchronous=False,
        )
        return self


__all__ = ["DEFAULT_SESSION_TRANSFORM_SOURCE", "SessionRecorderBlock"]
