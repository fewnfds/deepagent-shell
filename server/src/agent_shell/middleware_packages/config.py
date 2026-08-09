from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, model_validator


JsonScalar = str | int | float | bool


class MiddlewareConfigField(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    type: Literal["string", "integer", "number", "boolean"]
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1024)
    default: JsonScalar | None = None
    enum: list[JsonScalar] | None = Field(default=None, min_length=1, max_length=100)
    min_length: int | None = Field(default=None, alias="minLength", ge=0)
    max_length: int | None = Field(default=None, alias="maxLength", ge=0)
    pattern: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    content_media_type: Literal["text/plain", "text/x-python"] | None = Field(
        default=None,
        alias="contentMediaType",
    )
    format: Literal["python"] | None = None

    @model_validator(mode="after")
    def validate_keywords(self) -> "MiddlewareConfigField":
        string_options = (
            self.min_length,
            self.max_length,
            self.pattern,
            self.content_media_type,
            self.format,
        )
        number_options = (self.minimum, self.maximum)
        if self.type != "string" and any(value is not None for value in string_options):
            raise ValueError("string schema keywords require type=string")
        if self.type not in {"integer", "number"} and any(
            value is not None for value in number_options
        ):
            raise ValueError("numeric schema keywords require a numeric type")
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError("minLength may not exceed maxLength")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum may not exceed maximum")
        if self.enum is not None and len(self.enum) != len(
            {(type(value), value) for value in self.enum}
        ):
            raise ValueError("enum values must be unique")
        return self


class MiddlewareConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: Literal["object"]
    properties: dict[
        str, MiddlewareConfigField
    ] = Field(default_factory=dict, max_length=100)
    required: list[str] = Field(default_factory=list, max_length=100)
    additional_properties: Literal[False] = Field(
        default=False,
        alias="additionalProperties",
    )

    @model_validator(mode="after")
    def validate_object_schema(self) -> "MiddlewareConfigSchema":
        if len(self.required) != len(set(self.required)):
            raise ValueError("required property names must be unique")
        unknown = sorted(set(self.required) - set(self.properties))
        if unknown:
            raise ValueError("required properties must exist in properties")
        schema = self.as_json_schema()
        Draft202012Validator.check_schema(schema)
        for name, field in self.properties.items():
            field_schema = field.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            validator = Draft202012Validator(field_schema)
            if field.enum is not None and any(
                not validator.is_valid(value) for value in field.enum
            ):
                raise ValueError(f"the enum for {name!r} does not satisfy its type")
            if field.default is not None and not validator.is_valid(field.default):
                raise ValueError(f"the default for {name!r} does not satisfy its schema")
        return self

    def as_json_schema(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )


_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("python")
def _valid_python_source(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    try:
        ast.parse(value)
    except SyntaxError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class MiddlewareConfigIssue:
    path: tuple[str, ...]
    keyword: str


def validate_middleware_config(
    schema: dict[str, Any],
    config: object,
) -> MiddlewareConfigIssue | None:
    validator = Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)
    errors = sorted(
        validator.iter_errors(config),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return None
    error = errors[0]
    return MiddlewareConfigIssue(
        path=tuple(str(part) for part in error.absolute_path),
        keyword=str(error.validator or "schema"),
    )
