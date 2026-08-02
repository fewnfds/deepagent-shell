from __future__ import annotations

import re
from typing import Any

from agent_shell.validation.models import ValidationIssue


_SUBAGENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def subagent_binding_issues(
    bindings: list[dict[str, Any]],
    *,
    owner_id: str,
    owner_name: str,
) -> list[ValidationIssue]:
    """Return all binding semantic issues with field-level paths."""

    issues: list[ValidationIssue] = []
    seen_names: set[str] = set()
    for index, binding in enumerate(bindings):
        name = str(binding.get("name", ""))
        description = str(binding.get("description", ""))
        common = {
            "scope": "primary",
            "owner_id": owner_id,
            "owner_name": owner_name,
            "message_args": {},
        }
        if not name:
            issues.append(
                ValidationIssue(
                    code="contract.subagent_name_required",
                    path=f"subagents[{index}].name",
                    message="A Subagent name is required.",
                    message_key="validation.issue.contract.subagentNameRequired",
                    **common,
                )
            )
        elif _SUBAGENT_NAME.fullmatch(name) is None:
            issues.append(
                ValidationIssue(
                    code="contract.subagent_name_format_invalid",
                    path=f"subagents[{index}].name",
                    message="The Subagent name has an invalid format.",
                    message_key=(
                        "validation.issue.contract.subagentNameFormatInvalid"
                    ),
                    **common,
                )
            )
        if not description.strip():
            issues.append(
                ValidationIssue(
                    code="contract.subagent_description_required",
                    path=f"subagents[{index}].description",
                    message="A Subagent description is required.",
                    message_key=(
                        "validation.issue.contract.subagentDescriptionRequired"
                    ),
                    **common,
                )
            )
        if name and name in seen_names:
            issues.append(
                ValidationIssue(
                    code="contract.subagent_name_duplicate",
                    path=f"subagents[{index}].name",
                    message="Subagent names must be unique.",
                    message_key="validation.issue.contract.subagentNameDuplicate",
                    **common,
                )
            )
        elif name:
            seen_names.add(name)
    return issues
