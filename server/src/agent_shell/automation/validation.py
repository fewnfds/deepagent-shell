from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shell.automation.scripts import resolve_automation_script
from agent_shell.registries.errors import ResourceScanError
from agent_shell.validation.models import ValidationIssue


class AutomationValidationService:
    def __init__(self, *, scripts_dir: Path, runtime_root: Path) -> None:
        self._scripts_dir = scripts_dir
        self._runtime_root = runtime_root

    def configuration_issues(
        self,
        automation: dict[str, Any],
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        path_prefix: str,
    ) -> list[ValidationIssue]:
        if automation.get("mode") in {"inherit", "disabled"}:
            return []
        issues: list[ValidationIssue] = []
        has_lifecycle = False
        for index, binding in enumerate(automation.get("plugins", [])):
            plugin_id = str(binding.get("plugin_id", ""))
            path = f"{path_prefix}.plugins[{index}].plugin_id"
            try:
                resolved = resolve_automation_script(
                    plugin_id,
                    self._scripts_dir,
                    runtime_root=self._runtime_root,
                )
            except ResourceScanError:
                issues.append(
                    self._issue(
                        "automation.plugin_invalid",
                        scope,
                        owner_id,
                        owner_name,
                        path,
                        plugin_id,
                        "The referenced automation plugin is invalid.",
                        "pluginInvalid",
                    )
                )
                continue
            if resolved is None:
                issues.append(
                    self._issue(
                        "automation.plugin_not_found",
                        scope,
                        owner_id,
                        owner_name,
                        path,
                        plugin_id,
                        "The referenced automation plugin does not exist.",
                        "pluginNotFound",
                    )
                )
                continue
            metadata, _folder = resolved
            enabled = bool(binding.get("enabled", True))
            if enabled and "lifecycle" in metadata["entrypoints"]:
                has_lifecycle = True
            if not enabled:
                continue
            dependency_status = str(metadata["dependency_status"])
            if dependency_status == "ready":
                continue
            if dependency_status == "failed":
                code = "automation.plugin_dependencies_failed"
                key = "pluginDependenciesFailed"
                message = "The automation plugin dependencies could not be prepared."
            else:
                code = "automation.plugin_dependencies_restart_required"
                key = "pluginDependenciesRestartRequired"
                message = "Restart Agent Shell to prepare the automation plugin dependencies."
            issues.append(
                self._issue(
                    code,
                    scope,
                    owner_id,
                    owner_name,
                    path,
                    plugin_id,
                    message,
                    key,
                )
            )
        if automation.get("lifecycle_interval_seconds") is not None and not has_lifecycle:
            issues.append(
                ValidationIssue(
                    code="automation.lifecycle_plugin_required",
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path=f"{path_prefix}.lifecycle_interval_seconds",
                    message=(
                        "Lifecycle requires an enabled plugin that declares the lifecycle entrypoint."
                    ),
                    message_key="validation.issue.automation.lifecyclePluginRequired",
                    message_args={},
                )
            )
        return issues

    @staticmethod
    def _issue(
        code: str,
        scope: str,
        owner_id: str,
        owner_name: str,
        path: str,
        plugin_id: str,
        message: str,
        message_key: str,
    ) -> ValidationIssue:
        return ValidationIssue(
            code=code,
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
            path=path,
            message=message,
            message_key=f"validation.issue.automation.{message_key}",
            message_args={"plugin_id": plugin_id},
        )
