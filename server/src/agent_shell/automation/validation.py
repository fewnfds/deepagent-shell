from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_shell.automation.contracts import WORKFLOW_MODELS
from agent_shell.automation.scripts import resolve_automation_script
from agent_shell.registries.errors import ResourceScanError
from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport


class AutomationValidationService:
    def __init__(self, *, scripts_dir: Path, runtime_root: Path | None = None) -> None:
        self._scripts_dir = scripts_dir
        self._runtime_root = runtime_root

    def validate_workflow(
        self,
        workflow_type: str,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
        stored: bool = False,
    ) -> tuple[ValidationReport, dict[str, Any] | None]:
        model = WORKFLOW_MODELS[workflow_type]
        candidate = (
            {key: value for key, value in payload.items() if key != "id"}
            if stored
            else payload
        )
        try:
            validated_model = model.model_validate(candidate)
        except ValidationError as exc:
            return (
                report_from_validation_error(
                    exc,
                    stage=stage,
                    scope="automation",
                    owner_id=owner_id,
                    owner_name=str(payload.get("name", "")),
                    owner_type=workflow_type,
                ),
                None,
            )
        validated = validated_model.model_dump(mode="json")
        trigger = "hook" if workflow_type == "hook-workflow" else "lifecycle"
        nodes = (
            [
                (node, f"hooks.{hook}[{index}].script_id")
                for hook in (
                    "request_prepare",
                    "subagent_before_invoke",
                    "request_end",
                )
                for index, node in enumerate(validated["hooks"][hook])
            ]
            if workflow_type == "hook-workflow"
            else [
                (node, f"nodes[{index}].script_id")
                for index, node in enumerate(validated["nodes"])
            ]
        )
        issues: list[ValidationIssue] = []
        for node, path in nodes:
            script_id = str(node["script_id"])
            try:
                resolved = resolve_automation_script(
                    script_id,
                    self._scripts_dir,
                    runtime_root=self._runtime_root,
                )
            except ResourceScanError as exc:
                issues.append(
                    self._script_issue(
                        "automation.script_invalid",
                        owner_id,
                        str(validated["name"]),
                        path,
                        script_id,
                        str(exc),
                    )
                )
                continue
            if resolved is None:
                issues.append(
                    self._script_issue(
                        "automation.script_not_found",
                        owner_id,
                        str(validated["name"]),
                        path,
                        script_id,
                        "The referenced automation script does not exist.",
                    )
                )
                continue
            metadata, _ = resolved
            if trigger not in metadata["triggers"]:
                issues.append(
                    self._script_issue(
                        "automation.script_trigger_unsupported",
                        owner_id,
                        str(validated["name"]),
                        path,
                        script_id,
                        "The automation script does not support this workflow type.",
                    )
                )
                continue
            dependency_status = str(metadata["dependency_status"])
            if dependency_status != "ready":
                code = (
                    "automation.script_dependencies_failed"
                    if dependency_status == "failed"
                    else "automation.script_dependencies_restart_required"
                )
                message = (
                    "The automation plugin dependencies could not be prepared."
                    if dependency_status == "failed"
                    else "Restart Agent Shell to prepare the automation plugin dependencies."
                )
                issues.append(
                    self._script_issue(
                        code,
                        owner_id,
                        str(validated["name"]),
                        path,
                        script_id,
                        message,
                    )
                )
        return ValidationReport(stage=stage, issues=tuple(issues)), validated

    @staticmethod
    def _script_issue(
        code: str,
        owner_id: str,
        owner_name: str,
        path: str,
        script_id: str,
        message: str,
    ) -> ValidationIssue:
        message_keys = {
            "automation.script_invalid": "scriptInvalid",
            "automation.script_not_found": "scriptNotFound",
            "automation.script_trigger_unsupported": "scriptTriggerUnsupported",
            "automation.script_dependencies_failed": "scriptDependenciesFailed",
            "automation.script_dependencies_restart_required": (
                "scriptDependenciesRestartRequired"
            ),
        }
        return ValidationIssue(
            code=code,
            scope="automation",
            owner_id=owner_id,
            owner_name=owner_name,
            path=path,
            message=message,
            message_key=f"validation.issue.automation.{message_keys[code]}",
            message_args={"script_id": script_id},
        )
