from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent_shell.python_packages.config import PythonPackageConfigSchema
from agent_shell.python_packages.contracts import PACKAGE_ID_PATTERN
from agent_shell.python_packages.dependencies import (
    dependency_metadata,
    read_package_requirements,
)
from agent_shell.registries.errors import ResourceScanError


PythonPackageFamily = Literal["workflow-node", "middleware"]
PythonPackageAdapter = Literal["condition-router", "agent-middleware"]
_PACKAGE_ID = re.compile(PACKAGE_ID_PATTERN)


class PythonPackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    format_version: Literal[1]
    id: str = Field(min_length=36, max_length=36, pattern=PACKAGE_ID_PATTERN)
    family: PythonPackageFamily
    adapter: PythonPackageAdapter
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1024)
    config_schema: PythonPackageConfigSchema

    @model_validator(mode="after")
    def validate_adapter_family(self) -> "PythonPackageManifest":
        expected = {
            "condition-router": "workflow-node",
            "agent-middleware": "middleware",
        }[self.adapter]
        if self.family != expected:
            raise ValueError("adapter does not belong to the declared family")
        return self


def _is_link(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _read_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.invalidEncoding",
            f"{label} must use UTF-8 encoding.",
        ) from exc
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.readFailed",
            f"{label} could not be read.",
        ) from exc


def _scan_common(
    folder: Path,
    *,
    runtime_root: Path | None,
) -> tuple[dict[str, object], ast.Module]:
    if _is_link(folder):
        raise ResourceScanError(
            "resource.error.pythonPackage.linkUnsupported",
            "Python package folders may not be links or reparse points.",
        )
    try:
        package_entries = tuple(folder.rglob("*"))
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.readFailed",
            "The Python package directory could not be read.",
        ) from exc
    if any(_is_link(path) for path in package_entries):
        raise ResourceScanError(
            "resource.error.pythonPackage.linkUnsupported",
            "Python package contents may not be links or reparse points.",
        )
    manifest_path = folder / "package.json"
    main_path = folder / "main.py"
    if not manifest_path.is_file() or not main_path.is_file():
        raise ResourceScanError(
            "resource.error.pythonPackage.filesRequired",
            "The folder must contain package.json and main.py.",
        )
    if _is_link(manifest_path) or _is_link(main_path):
        raise ResourceScanError(
            "resource.error.pythonPackage.linkUnsupported",
            "Python package files may not be links or reparse points.",
        )
    try:
        raw_manifest = json.loads(_read_text(manifest_path, label="package.json"))
    except json.JSONDecodeError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.manifestInvalid",
            "package.json must contain a valid JSON object.",
        ) from exc
    try:
        manifest = PythonPackageManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.manifestInvalid",
            "package.json does not satisfy the current manifest contract.",
        ) from exc
    if manifest.id != folder.name:
        raise ResourceScanError(
            "resource.error.pythonPackage.idMismatch",
            "The manifest id must match the folder name.",
            {"declared_id": manifest.id},
        )
    source = _read_text(main_path, label="main.py")
    try:
        tree = ast.parse(source, filename=str(main_path))
    except SyntaxError as exc:
        raise ResourceScanError(
            "resource.error.pythonPackage.syntax",
            f"main.py contains a syntax error on line {exc.lineno or 1}.",
            {"line": exc.lineno or 1},
        ) from exc
    requirements = read_package_requirements(folder)
    metadata = {
        **manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
        "folder": folder.name,
        **dependency_metadata(
            f"python-package:{manifest.id}", requirements, runtime_root
        ),
    }
    return metadata, tree


def _validate_factory(
    tree: ast.Module,
    *,
    name: str,
    parameters: tuple[str, ...],
) -> None:
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    signature = ", ".join(parameters)
    if len(functions) != 1 or isinstance(functions[0], ast.AsyncFunctionDef):
        raise ResourceScanError(
            "resource.error.pythonPackage.entrypointRequired",
            f"main.py must define exactly one module-level def {name}({signature}).",
        )
    function = functions[0]
    positional = [*function.args.posonlyargs, *function.args.args]
    if (
        [argument.arg for argument in positional] != list(parameters)
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
        or function.args.defaults
    ):
        raise ResourceScanError(
            "resource.error.pythonPackage.entrypointSignatureInvalid",
            f"The {name} entrypoint must accept exactly: {signature}.",
        )


def scan_python_package(
    folder: Path,
    *,
    family: PythonPackageFamily,
    adapter: PythonPackageAdapter,
    factory_name: str,
    factory_parameters: tuple[str, ...],
    runtime_root: Path | None = None,
) -> dict[str, object]:
    metadata, tree = _scan_common(folder, runtime_root=runtime_root)
    if metadata["family"] != family or metadata["adapter"] != adapter:
        raise ResourceScanError(
            "resource.error.pythonPackage.typeMismatch",
            "The Python package does not implement the expected adapter.",
            {"expected_family": family, "expected_adapter": adapter},
        )
    _validate_factory(
        tree,
        name=factory_name,
        parameters=factory_parameters,
    )
    return metadata


def resolve_python_package(
    package_id: str,
    directory: Path,
    *,
    family: PythonPackageFamily,
    adapter: PythonPackageAdapter,
    factory_name: str,
    factory_parameters: tuple[str, ...],
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path] | None:
    if not _PACKAGE_ID.fullmatch(package_id):
        return None
    folder = directory / package_id
    if not folder.is_dir():
        return None
    return (
        scan_python_package(
            folder,
            family=family,
            adapter=adapter,
            factory_name=factory_name,
            factory_parameters=factory_parameters,
            runtime_root=runtime_root,
        ),
        folder,
    )


def scan_python_packages(
    directory: Path,
    *,
    family: PythonPackageFamily,
    adapter: PythonPackageAdapter,
    factory_name: str,
    factory_parameters: tuple[str, ...],
    runtime_root: Path | None = None,
) -> dict[str, object]:
    catalog: list[dict[str, object]] = []
    errors: dict[str, dict[str, object]] = {}
    if not directory.exists():
        return {"catalog": catalog, "errors": errors}
    for folder in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
        if not folder.is_dir():
            continue
        try:
            metadata, tree = _scan_common(folder, runtime_root=runtime_root)
            if metadata["family"] != family or metadata["adapter"] != adapter:
                continue
            _validate_factory(
                tree,
                name=factory_name,
                parameters=factory_parameters,
            )
            catalog.append(metadata)
        except ResourceScanError as exc:
            errors[folder.name] = exc.as_dict()
    return {"catalog": catalog, "errors": errors}


__all__ = [
    "PythonPackageAdapter",
    "PythonPackageFamily",
    "PythonPackageManifest",
    "resolve_python_package",
    "scan_python_package",
    "scan_python_packages",
]
