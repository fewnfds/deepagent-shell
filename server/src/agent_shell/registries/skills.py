from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import yaml

from agent_shell.registries.errors import ResourceScanError


SKILL_NAME_MAX_LENGTH = 64
SKILL_DESCRIPTION_MAX_LENGTH = 1024


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _skill_name_error(value: str) -> ResourceScanError | None:
    if not value or len(value) > SKILL_NAME_MAX_LENGTH:
        return ResourceScanError(
            "resource.error.skill.nameLength",
            f"Skill name must contain 1–{SKILL_NAME_MAX_LENGTH} characters.",
            {"max_length": SKILL_NAME_MAX_LENGTH},
        )
    if value.startswith("-") or value.endswith("-") or "--" in value:
        return ResourceScanError(
            "resource.error.skill.nameHyphen",
            (
                "Skill name must use single hyphens as separators and must not "
                "start or end with a hyphen."
            ),
        )
    if any(
        character != "-"
        and not (
            (character.isalpha() and character.islower())
            or character.isdigit()
        )
        for character in value
    ):
        return ResourceScanError(
            "resource.error.skill.nameCharacters",
            "Skill name may contain only lowercase letters, digits, and hyphens.",
        )
    return None


def skill_name_issue(value: str) -> str:
    issue = _skill_name_error(value)
    return str(issue) if issue is not None else ""


def _parse_frontmatter(content: str) -> dict[str, Any]:
    lines = content.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ResourceScanError(
            "resource.error.skill.frontmatterMissing",
            "SKILL.md is missing YAML frontmatter.",
        )
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ResourceScanError(
            "resource.error.skill.frontmatterUnclosed",
            "SKILL.md frontmatter is not closed.",
        ) from exc
    try:
        parsed = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ResourceScanError(
            "resource.error.skill.frontmatterInvalidYaml",
            "SKILL.md frontmatter is not valid YAML.",
        ) from exc
    if not isinstance(parsed, dict):
        raise ResourceScanError(
            "resource.error.skill.frontmatterObjectRequired",
            "SKILL.md frontmatter must be an object.",
        )
    return parsed


def scan_skill_folder(folder: Path) -> dict[str, Any]:
    issue = _skill_name_error(folder.name)
    if issue is not None:
        raise issue
    skill_path = folder / "SKILL.md"
    if not skill_path.is_file():
        raise ResourceScanError(
            "resource.error.skill.manifestMissing",
            "The folder does not contain an uppercase SKILL.md file.",
        )
    try:
        content = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.skill.readFailed",
            "SKILL.md could not be read.",
        ) from exc
    except UnicodeError as exc:
        raise ResourceScanError(
            "resource.error.skill.invalidEncoding",
            "SKILL.md must use UTF-8 encoding.",
        ) from exc
    frontmatter = _parse_frontmatter(content)

    declared_name = frontmatter.get("name")
    if not isinstance(declared_name, str) or not declared_name:
        raise ResourceScanError(
            "resource.error.skill.nameMissing",
            "SKILL.md frontmatter is missing a string name.",
        )
    issue = _skill_name_error(declared_name)
    if issue is not None:
        raise issue
    if declared_name != folder.name:
        raise ResourceScanError(
            "resource.error.skill.nameMismatch",
            (
                "The folder name does not match frontmatter name "
                f"{declared_name!r}."
            ),
            {"declared_name": declared_name},
        )

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ResourceScanError(
            "resource.error.skill.descriptionMissing",
            "SKILL.md frontmatter is missing a string description.",
        )
    description = description.strip()
    if len(description) > SKILL_DESCRIPTION_MAX_LENGTH:
        raise ResourceScanError(
            "resource.error.skill.descriptionTooLong",
            (
                "Skill description must contain at most "
                f"{SKILL_DESCRIPTION_MAX_LENGTH} characters."
            ),
            {"max_length": SKILL_DESCRIPTION_MAX_LENGTH},
        )
    return {
        "name": declared_name,
        "folder": folder.name,
        "description": description,
    }


def scan_skill_templates(skills_dir: Path) -> dict[str, Any]:
    catalog: list[dict[str, Any]] = []
    errors: dict[str, dict[str, object]] = {}
    if not skills_dir.exists():
        return {"catalog": catalog, "errors": errors}

    def visit(parent: Path) -> None:
        try:
            children = sorted(
                parent.iterdir(), key=lambda path: path.name.casefold()
            )
        except OSError as exc:
            relative = parent.relative_to(skills_dir).as_posix() or "."
            errors[relative] = {
                "message_key": "resource.error.skill.readFailed",
                "message": "The Skill template directory could not be read.",
                "details": str(exc),
            }
            return
        for folder in children:
            relative_path = folder.relative_to(skills_dir).as_posix()
            if not folder.is_dir():
                continue
            if _is_reparse_point(folder):
                errors[relative_path] = {
                    "message_key": "resource.error.skill.pathUnsupported",
                    "message": "Symbolic links and reparse points are not supported.",
                }
                continue
            manifest = folder / "SKILL.md"
            if manifest.exists():
                try:
                    item = scan_skill_folder(folder)
                except ResourceScanError as exc:
                    errors[relative_path] = exc.as_dict()
                else:
                    catalog.append(
                        {
                            **item,
                            "template_path": relative_path,
                        }
                    )
                # A first SKILL.md is the complete ownership boundary, even if
                # its contents are invalid.
                continue
            visit(folder)

    visit(skills_dir)
    catalog.sort(key=lambda item: (str(item["template_path"]).casefold(), str(item["name"])))
    return {"catalog": catalog, "errors": errors}


def scan_private_skill_package(skills_dir: Path) -> dict[str, Any]:
    catalog: list[dict[str, Any]] = []
    errors: dict[str, dict[str, object]] = {}
    if not skills_dir.exists():
        return {"catalog": catalog, "errors": errors}
    try:
        children = sorted(skills_dir.iterdir(), key=lambda path: path.name.casefold())
    except OSError as exc:
        return {
            "catalog": catalog,
            "errors": {
                ".": {
                    "message_key": "resource.error.skill.readFailed",
                    "message": "The private Skill package could not be read.",
                    "details": str(exc),
                }
            },
        }
    names: dict[str, str] = {}
    for folder in children:
        if not folder.is_dir():
            continue
        relative_path = folder.name
        if _is_reparse_point(folder):
            errors[relative_path] = {
                "message_key": "resource.error.skill.pathUnsupported",
                "message": "Symbolic links and reparse points are not supported.",
            }
            continue
        try:
            catalog.append(scan_skill_folder(folder))
        except ResourceScanError as exc:
            errors[relative_path] = exc.as_dict()
            continue
        name = str(catalog[-1]["name"])
        previous = names.get(name)
        if previous is not None:
            errors[relative_path] = {
                "message_key": "resource.error.skill.duplicateName",
                "message": f"The private Skill package contains duplicate Skill name {name!r}.",
                "details": {"name": name, "other_folder": previous},
            }
            catalog.pop()
        else:
            names[name] = relative_path
    catalog.sort(key=lambda item: str(item["name"]).casefold())
    return {"catalog": catalog, "errors": errors}


def scan_skills(skills_dir: Path) -> dict[str, Any]:
    """Backward-neutral registry entry point for the template catalog."""

    return scan_skill_templates(skills_dir)
