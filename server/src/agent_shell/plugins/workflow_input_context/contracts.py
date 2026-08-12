from __future__ import annotations

import ast
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from agent_shell.python_requirements import parse_python_requirements


PluginText = Annotated[str, StringConstraints(strip_whitespace=False)]
DEFAULT_CUSTOM_TRANSFORM_SOURCE = (
    "def transform(messages, read_file, config, state, context):\n"
    "    # import package_name\n"
    "    # Write custom Python here.\n"
    "    return messages\n"
)
VirtualPath = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
]
SlotRole = Literal["user", "assistant", "system"]


def validate_virtual_path(value: str) -> str:
    if not value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("filesystem paths must be absolute virtual paths")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts[1:]):
        raise ValueError("filesystem paths must not contain empty or dot segments")
    return value


class WorkflowInputContextSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = True
    role: SlotRole = "system"
    file: VirtualPath | None = None
    fallback_files: list[VirtualPath] = Field(default_factory=list, max_length=20)
    literal: PluginText = Field(default="", max_length=1_000_000)
    max_chars: int | None = Field(default=None, ge=1, le=1_000_000)
    truncate_if_missing: bool = False

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str | None) -> str | None:
        return validate_virtual_path(value) if value is not None else None

    @field_validator("fallback_files")
    @classmethod
    def validate_fallback_files(cls, values: list[str]) -> list[str]:
        normalized = [validate_virtual_path(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("fallback_files must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_source(self) -> "WorkflowInputContextSlot":
        if self.file is None and not self.fallback_files and not self.literal:
            if not self.truncate_if_missing:
                raise ValueError(
                    "a slot requires file, fallback_files, literal, or truncate_if_missing"
                )
        return self


class WorkflowInputContextBlock(BaseModel):
    """Configuration for the first-party input-context middleware."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=120)]
    enabled: bool = True
    custom_transform_enabled: bool = False
    custom_transform_source: PluginText = Field(
        default=DEFAULT_CUSTOM_TRANSFORM_SOURCE,
        max_length=100_000,
    )
    system_promote_enabled: bool = True
    system_promote_min_chars: int = Field(default=10, ge=0, le=1_000_000)
    demote_non_top_system: bool = True
    slots: list[WorkflowInputContextSlot] = Field(default_factory=list, max_length=100)
    python_requirements: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("python_requirements")
    @classmethod
    def validate_python_requirements(cls, values: list[str]) -> list[str]:
        return list(parse_python_requirements(values).values)

    @model_validator(mode="after")
    def validate_transform_source(self) -> "WorkflowInputContextBlock":
        source = self.custom_transform_source.strip()
        if not source:
            return self
        try:
            tree = ast.parse(source, filename="workflow_input_context_transform.py")
        except SyntaxError as exc:
            raise ValueError("custom_transform_source contains invalid Python") from exc
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        if any(isinstance(node, ast.AsyncFunctionDef) and node.name == "transform" for node in tree.body):
            raise ValueError("transform must be a synchronous function")
        if not any(node.name == "transform" for node in functions):
            raise ValueError("custom_transform_source must define transform")
        return self


__all__ = [
    "DEFAULT_CUSTOM_TRANSFORM_SOURCE",
    "SlotRole",
    "WorkflowInputContextBlock",
    "WorkflowInputContextSlot",
    "validate_virtual_path",
]
