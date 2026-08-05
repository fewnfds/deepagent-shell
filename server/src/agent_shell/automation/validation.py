from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shell.automation.config_schema import validate_automation_config
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
        issues: list[ValidationIssue] = []
        for binding_kind, required_entrypoints in (
            ("hooks", {"middleware", "prepare"}),
            ("periodic", {"lifecycle"}),
        ):
            selection = automation.get(binding_kind, [])
            if isinstance(selection, dict):
                if selection.get("mode", "inherit") != "replace":
                    continue
                bindings = selection.get("plugins", [])
                binding_path = f"{path_prefix}.{binding_kind}.plugins"
            else:
                bindings = selection
                binding_path = f"{path_prefix}.{binding_kind}"
            issues.extend(
                self._binding_issues(
                    bindings,
                    binding_kind=binding_kind,
                    required_entrypoints=required_entrypoints,
                    scope=scope,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path_prefix=binding_path,
                )
            )
        return issues

    def _binding_issues(
        self,
        bindings: list[dict[str, Any]],
        *,
        binding_kind: str,
        required_entrypoints: set[str],
        scope: str,
        owner_id: str,
        owner_name: str,
        path_prefix: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for index, binding in enumerate(bindings):
            plugin_id = str(binding.get("plugin_id", ""))
            path = f"{path_prefix}[{index}].plugin_id"
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
            if not required_entrypoints.intersection(metadata["entrypoints"]):
                issues.append(
                    ValidationIssue(
                        code="automation.plugin_entrypoint_mismatch",
                        scope=scope,
                        owner_id=owner_id,
                        owner_name=owner_name,
                        path=path,
                        message=(
                            f"The automation plugin does not provide a {binding_kind} entrypoint."
                        ),
                        message_key=(
                            "validation.issue.automation.pluginEntrypointMismatch"
                        ),
                        message_args={
                            "plugin_id": plugin_id,
                            "kind": binding_kind,
                        },
                    )
                )
                continue
            config_issue = validate_automation_config(
                metadata["config_schema"],
                binding.get("config", {}),
            )
            if config_issue is not None:
                config_path = f"{path_prefix}[{index}].config"
                if config_issue.path:
                    config_path += "." + ".".join(config_issue.path)
                issues.append(
                    ValidationIssue(
                        code="automation.plugin_config_invalid",
                        scope=scope,
                        owner_id=owner_id,
                        owner_name=owner_name,
                        path=config_path,
                        message=(
                            "The automation plugin configuration does not satisfy "
                            "its declared schema."
                        ),
                        message_key=(
                            "validation.issue.automation.pluginConfigInvalid"
                        ),
                        message_args={
                            "plugin_id": plugin_id,
                            "keyword": config_issue.keyword,
                        },
                    )
                )
                continue
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
