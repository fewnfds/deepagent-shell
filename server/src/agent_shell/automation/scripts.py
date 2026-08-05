from __future__ import annotations

import ast
import json
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_shell.automation.dependencies import (
    dependency_metadata,
    read_plugin_requirements,
)
from agent_shell.automation.config_schema import AutomationConfigSchema
from agent_shell.registries.errors import ResourceScanError


PluginEntrypoint = Literal["middleware", "prepare", "lifecycle", "complete"]
_ENTRYPOINT_FUNCTIONS: dict[str, tuple[str, bool]] = {
    "middleware": ("create_middleware", False),
    "prepare": ("prepare", True),
    "lifecycle": ("lifecycle", True),
    "complete": ("complete", True),
}


class AutomationScriptManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_version: Literal[3]
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1024)
    entrypoints: list[PluginEntrypoint] = Field(min_length=1, max_length=4)
    config_schema: AutomationConfigSchema

    @field_validator("entrypoints")
    @classmethod
    def unique_entrypoints(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("plugin entrypoints must be unique")
        if not {"middleware", "prepare", "lifecycle"}.intersection(value):
            raise ValueError(
                "plugin must provide middleware, prepare, or lifecycle"
            )
        return value


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
            "resource.error.automationScript.invalidEncoding",
            f"{label} must use UTF-8 encoding.",
        ) from exc
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.automationScript.readFailed",
            f"{label} could not be read.",
        ) from exc


def _validate_entrypoint(tree: ast.Module, entrypoint: str) -> None:
    function_name, must_be_async = _ENTRYPOINT_FUNCTIONS[entrypoint]
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(functions) != 1 or isinstance(functions[0], ast.AsyncFunctionDef) != must_be_async:
        declaration = "async def" if must_be_async else "def"
        raise ResourceScanError(
            "resource.error.automationScript.entrypointRequired",
            f"main.py must define exactly one module-level {declaration} {function_name}(ctx).",
            {"entrypoint": entrypoint},
        )
    function = functions[0]
    positional = [*function.args.posonlyargs, *function.args.args]
    if (
        len(positional) != 1
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
    ):
        raise ResourceScanError(
            "resource.error.automationScript.entrypointSignatureInvalid",
            f"The {function_name} entrypoint must accept exactly one positional ctx argument.",
            {"entrypoint": entrypoint},
        )


def scan_automation_script_folder(
    folder: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    if _is_link(folder):
        raise ResourceScanError(
            "resource.error.automationScript.linkUnsupported",
            "Automation plugin folders may not be links or reparse points.",
        )
    manifest_path = folder / "script.json"
    main_path = folder / "main.py"
    if not manifest_path.is_file() or not main_path.is_file():
        raise ResourceScanError(
            "resource.error.automationScript.filesRequired",
            "The folder must contain script.json and main.py.",
        )
    if _is_link(manifest_path) or _is_link(main_path):
        raise ResourceScanError(
            "resource.error.automationScript.linkUnsupported",
            "Automation plugin files may not be links or reparse points.",
        )
    try:
        raw_manifest = json.loads(_read_text(manifest_path, label="script.json"))
    except json.JSONDecodeError as exc:
        raise ResourceScanError(
            "resource.error.automationScript.manifestInvalid",
            "script.json must contain a valid JSON object.",
        ) from exc
    try:
        manifest = AutomationScriptManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        raise ResourceScanError(
            "resource.error.automationScript.manifestInvalid",
            "script.json does not satisfy the current manifest contract.",
        ) from exc
    if manifest.id != folder.name:
        raise ResourceScanError(
            "resource.error.automationScript.idMismatch",
            "The manifest id must match the folder name.",
            {"declared_id": manifest.id},
        )
    source = _read_text(main_path, label="main.py")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ResourceScanError(
            "resource.error.automationScript.syntax",
            f"main.py contains a syntax error on line {exc.lineno or 1}.",
            {"line": exc.lineno or 1},
        ) from exc
    for entrypoint in manifest.entrypoints:
        _validate_entrypoint(tree, entrypoint)
    requirements = read_plugin_requirements(folder)
    return {
        **manifest.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        "folder": folder.name,
        **dependency_metadata(manifest.id, requirements, runtime_root),
    }


def resolve_automation_script(
    script_id: str,
    directory: Path,
    *,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path] | None:
    if not script_id or Path(script_id).name != script_id:
        return None
    folder = directory / script_id
    if not folder.is_dir():
        return None
    return scan_automation_script_folder(folder, runtime_root=runtime_root), folder


def scan_automation_scripts(
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
            item = scan_automation_script_folder(folder, runtime_root=runtime_root)
            script_id = str(item["id"])
            if script_id in seen_ids:
                raise ResourceScanError(
                    "resource.error.automationScript.idDuplicate",
                    "Automation plugin ids must be unique.",
                )
            seen_ids.add(script_id)
            catalog.append(item)
        except ResourceScanError as exc:
            errors[folder.name] = exc.as_dict()
    return {"catalog": catalog, "errors": errors}
