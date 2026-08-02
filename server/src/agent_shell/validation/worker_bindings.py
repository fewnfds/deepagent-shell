from __future__ import annotations

import re
from typing import Any

from agent_shell.validation.models import ValidationIssue


_WORKER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def worker_binding_issues(
    bindings: list[dict[str, Any]],
    *,
    owner_id: str,
    owner_name: str,
) -> list[ValidationIssue]:
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
                    code="contract.worker_name_required",
                    path=f"workers[{index}].name",
                    message="A Context Worker name is required.",
                    message_key="validation.issue.contract.workerNameRequired",
                    **common,
                )
            )
        elif _WORKER_NAME.fullmatch(name) is None:
            issues.append(
                ValidationIssue(
                    code="contract.worker_name_format_invalid",
                    path=f"workers[{index}].name",
                    message="The Context Worker name has an invalid format.",
                    message_key="validation.issue.contract.workerNameFormatInvalid",
                    **common,
                )
            )
        if not description.strip():
            issues.append(
                ValidationIssue(
                    code="contract.worker_description_required",
                    path=f"workers[{index}].description",
                    message="A Context Worker description is required.",
                    message_key="validation.issue.contract.workerDescriptionRequired",
                    **common,
                )
            )
        if name and name in seen_names:
            issues.append(
                ValidationIssue(
                    code="contract.worker_name_duplicate",
                    path=f"workers[{index}].name",
                    message="Context Worker names must be unique.",
                    message_key="validation.issue.contract.workerNameDuplicate",
                    **common,
                )
            )
        elif name:
            seen_names.add(name)
    return issues
