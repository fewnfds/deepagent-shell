from __future__ import annotations

import ast
import json
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_shell.middleware_packages.dependencies import (
    dependency_metadata,
    read_package_requirements,
)
from agent_shell.middleware_packages.config import MiddlewareConfigSchema
from agent_shell.registries.errors import ResourceScanError


class MiddlewarePackageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_version: Literal[1]
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1024)
    config_schema: MiddlewareConfigSchema


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
            "resource.error.middlewarePackage.invalidEncoding",
            f"{label} must use UTF-8 encoding.",
        ) from exc
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.readFailed",
            f"{label} could not be read.",
        ) from exc


def _validate_entrypoint(tree: ast.Module) -> None:
    function_name = "create_middleware"
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(functions) != 1 or isinstance(functions[0], ast.AsyncFunctionDef):
        raise ResourceScanError(
            "resource.error.middlewarePackage.entrypointRequired",
            f"main.py must define exactly one module-level def {function_name}(config, agent).",
        )
    function = functions[0]
    positional = [*function.args.posonlyargs, *function.args.args]
    if (
        len(positional) != 2
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
    ):
        raise ResourceScanError(
            "resource.error.middlewarePackage.entrypointSignatureInvalid",
            f"The {function_name} entrypoint must accept exactly two positional arguments: config and agent.",
        )


def scan_middleware_package(
    folder: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    if _is_link(folder):
        raise ResourceScanError(
            "resource.error.middlewarePackage.linkUnsupported",
            "Middleware package folders may not be links or reparse points.",
        )
    manifest_path = folder / "middleware.json"
    main_path = folder / "main.py"
    if not manifest_path.is_file() or not main_path.is_file():
        raise ResourceScanError(
            "resource.error.middlewarePackage.filesRequired",
            "The folder must contain middleware.json and main.py.",
        )
    if _is_link(manifest_path) or _is_link(main_path):
        raise ResourceScanError(
            "resource.error.middlewarePackage.linkUnsupported",
            "Middleware package files may not be links or reparse points.",
        )
    try:
        raw_manifest = json.loads(_read_text(manifest_path, label="middleware.json"))
    except json.JSONDecodeError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.manifestInvalid",
            "middleware.json must contain a valid JSON object.",
        ) from exc
    try:
        manifest = MiddlewarePackageManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.manifestInvalid",
            "middleware.json does not satisfy the current manifest contract.",
        ) from exc
    if manifest.id != folder.name:
        raise ResourceScanError(
            "resource.error.middlewarePackage.idMismatch",
            "The manifest id must match the folder name.",
            {"declared_id": manifest.id},
        )
    source = _read_text(main_path, label="main.py")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.syntax",
            f"main.py contains a syntax error on line {exc.lineno or 1}.",
            {"line": exc.lineno or 1},
        ) from exc
    _validate_entrypoint(tree)
    requirements = read_package_requirements(folder)
    return {
        **manifest.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        "folder": folder.name,
        **dependency_metadata(
            f"middleware-package:{manifest.id}", requirements, runtime_root
        ),
    }


def resolve_middleware_package(
    package_id: str,
    directory: Path,
    *,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path] | None:
    if not package_id or Path(package_id).name != package_id:
        return None
    folder = directory / package_id
    if not folder.is_dir():
        return None
    return scan_middleware_package(folder, runtime_root=runtime_root), folder


def scan_middleware_packages(
    directory: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    catalog: list[dict[str, object]] = []
    errors: dict[str, dict[str, object]] = {}
    seen_ids: set[str] = set()
    if not directory.exists():
        return {"catalog": catalog, "errors": errors}
    for folder in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
        if not folder.is_dir():
            continue
        try:
            item = scan_middleware_package(folder, runtime_root=runtime_root)
            package_id = str(item["id"])
            if package_id in seen_ids:
                raise ResourceScanError(
                    "resource.error.middlewarePackage.idDuplicate",
                    "Middleware package ids must be unique.",
                )
            seen_ids.add(package_id)
            catalog.append(item)
        except ResourceScanError as exc:
            errors[folder.name] = exc.as_dict()
    return {"catalog": catalog, "errors": errors}
