from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


PACKAGE_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


PackageId = Annotated[
    str,
    Field(min_length=36, max_length=36, pattern=PACKAGE_ID_PATTERN),
]


class PythonPackageBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    package_id: PackageId
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


__all__ = ["PACKAGE_ID_PATTERN", "PackageId", "PythonPackageBinding"]
