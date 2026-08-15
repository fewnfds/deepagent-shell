from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


PACKAGE_ID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_UUID_FRAGMENT = PACKAGE_ID_PATTERN.removeprefix("^").removesuffix("$")
PACKAGE_FOLDER_PATTERN = (
    rf"^(?P<owner>{_UUID_FRAGMENT})--"
    r"(?P<template>[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)--"
    rf"(?P<instance>{_UUID_FRAGMENT})$"
)
_PACKAGE_FOLDER = re.compile(PACKAGE_FOLDER_PATTERN)


PackageId = Annotated[
    str,
    Field(min_length=36, max_length=36, pattern=PACKAGE_ID_PATTERN),
]


PackageFolder = Annotated[
    str,
    Field(min_length=76, max_length=140, pattern=PACKAGE_FOLDER_PATTERN),
]


class PythonPackageReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    folder: PackageFolder
    config: dict[str, Any] = Field(default_factory=dict)


def parse_package_folder(folder: str) -> tuple[str, str, str] | None:
    matched = _PACKAGE_FOLDER.fullmatch(folder)
    if matched is None:
        return None
    return (
        matched.group("owner"),
        matched.group("template"),
        matched.group("instance"),
    )


__all__ = [
    "PACKAGE_FOLDER_PATTERN",
    "PACKAGE_ID_PATTERN",
    "PackageFolder",
    "PackageId",
    "PythonPackageReference",
    "parse_package_folder",
]
