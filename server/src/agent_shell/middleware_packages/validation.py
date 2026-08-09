from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_shell.middleware_packages.config import validate_middleware_config
from agent_shell.middleware_packages.packages import resolve_middleware_package
from agent_shell.registries.errors import ResourceScanError
from agent_shell.validation.models import ValidationIssue


class MiddlewarePackageValidationService:
    def __init__(self, *, packages_dir: Path, runtime_root: Path) -> None:
        self._packages_dir = packages_dir
        self._runtime_root = runtime_root

    def configuration_issues(
        self,
        bindings: list[dict[str, Any]],
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        path_prefix: str,
    ) -> list[ValidationIssue]:
        return self._binding_issues(
            bindings,
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
            path_prefix=path_prefix,
        )

    def _binding_issues(
        self,
        bindings: list[dict[str, Any]],
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        path_prefix: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for index, binding in enumerate(bindings):
            package_id = str(binding.get("package_id", ""))
            path = f"{path_prefix}[{index}].package_id"
            try:
                resolved = resolve_middleware_package(
                    package_id,
                    self._packages_dir,
                    runtime_root=self._runtime_root,
                )
            except ResourceScanError:
                issues.append(
                    self._issue(
                        "middleware_package.invalid",
                        scope,
                        owner_id,
                        owner_name,
                        path,
                        package_id,
                        "The referenced Middleware package is invalid.",
                        "invalid",
                    )
                )
                continue
            if resolved is None:
                issues.append(
                    self._issue(
                        "middleware_package.not_found",
                        scope,
                        owner_id,
                        owner_name,
                        path,
                        package_id,
                        "The referenced Middleware package does not exist.",
                        "notFound",
                    )
                )
                continue
            metadata, _folder = resolved
            config_issue = validate_middleware_config(
                metadata["config_schema"],
                binding.get("config", {}),
            )
            if config_issue is not None:
                config_path = f"{path_prefix}[{index}].config"
                if config_issue.path:
                    config_path += "." + ".".join(config_issue.path)
                issues.append(
                    ValidationIssue(
                        code="middleware_package.config_invalid",
                        scope=scope,
                        owner_id=owner_id,
                        owner_name=owner_name,
                        path=config_path,
                        message=(
                            "The Middleware package configuration does not satisfy "
                            "its declared schema."
                        ),
                        message_key="validation.issue.middlewarePackage.configInvalid",
                        message_args={
                            "package_id": package_id,
                            "keyword": config_issue.keyword,
                        },
                    )
                )
                continue
            if not bool(binding.get("enabled", True)):
                continue
            dependency_status = str(metadata["dependency_status"])
            if dependency_status == "ready":
                continue
            if dependency_status == "failed":
                code = "middleware_package.dependencies_failed"
                key = "dependenciesFailed"
                message = "The Middleware package dependencies could not be prepared."
            else:
                code = "middleware_package.dependencies_restart_required"
                key = "dependenciesRestartRequired"
                message = (
                    "Restart Agent Shell to prepare the Middleware package dependencies."
                )
            issues.append(
                self._issue(
                    code,
                    scope,
                    owner_id,
                    owner_name,
                    path,
                    package_id,
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
        package_id: str,
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
            message_key=f"validation.issue.middlewarePackage.{message_key}",
            message_args={"package_id": package_id},
        )
