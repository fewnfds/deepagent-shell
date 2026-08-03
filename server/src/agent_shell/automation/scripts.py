from __future__ import annotations

import ast
import json
import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_shell.registries.errors import ResourceScanError


class AutomationScriptManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_version: Literal[1]
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1024)
    triggers: list[Literal["hook", "lifecycle"]] = Field(min_length=1, max_length=2)

    @field_validator("triggers")
    @classmethod
    def unique_triggers(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("script triggers must be unique")
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


def scan_automation_script_folder(folder: Path) -> dict[str, object]:
    if _is_link(folder):
        raise ResourceScanError(
            "resource.error.automationScript.linkUnsupported",
            "Automation script folders may not be links or reparse points.",
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
            "Automation script files may not be links or reparse points.",
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
    entrypoints = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run"
    ]
    if len(entrypoints) != 1 or not isinstance(entrypoints[0], ast.AsyncFunctionDef):
        raise ResourceScanError(
            "resource.error.automationScript.asyncRunRequired",
            "main.py must define exactly one module-level async def run(ctx).",
        )
    entrypoint = entrypoints[0]
    positional = [*entrypoint.args.posonlyargs, *entrypoint.args.args]
    if (
        len(positional) != 1
        or entrypoint.args.vararg is not None
        or entrypoint.args.kwarg is not None
        or entrypoint.args.kwonlyargs
    ):
        raise ResourceScanError(
            "resource.error.automationScript.runSignatureInvalid",
            "The run entrypoint must accept exactly one positional ctx argument.",
        )
    return {
        **manifest.model_dump(mode="json"),
        "folder": folder.name,
    }


def resolve_automation_script(
    script_id: str,
    directory: Path,
) -> tuple[dict[str, object], Path] | None:
    if not script_id or Path(script_id).name != script_id:
        return None
    folder = directory / script_id
    if not folder.is_dir():
        return None
    return scan_automation_script_folder(folder), folder


def scan_automation_scripts(directory: Path) -> dict[str, object]:
    catalog: list[dict[str, object]] = []
    errors: dict[str, dict[str, object]] = {}
    seen_ids: set[str] = set()
    if not directory.exists():
        return {"catalog": catalog, "errors": errors}
    for folder in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
        if not folder.is_dir():
            continue
        try:
            item = scan_automation_script_folder(folder)
            script_id = str(item["id"])
            if script_id in seen_ids:
                raise ResourceScanError(
                    "resource.error.automationScript.idDuplicate",
                    "Automation script ids must be unique.",
                )
            seen_ids.add(script_id)
            catalog.append(item)
        except ResourceScanError as exc:
            errors[folder.name] = exc.as_dict()
    return {"catalog": catalog, "errors": errors}

