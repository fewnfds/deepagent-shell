from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


PackageId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$"),
]


class MiddlewarePackageBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    package_id: PackageId
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
