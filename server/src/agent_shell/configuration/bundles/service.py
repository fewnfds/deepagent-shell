from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from agent_shell.configuration.bundles.contracts import BundleRoot, ImportResolutions
from agent_shell.configuration.bundles.exporting import (
    ConfigurationBundleExporter,
    ExportedBundle,
)
from agent_shell.configuration.bundles.errors import BundleImportError
from agent_shell.configuration.bundles.planning import BundleImportPlanner
from agent_shell.configuration.bundles.transactions import commit_prepared_import
from agent_shell.storage.file_config import FileConfigRepository


class ConfigurationBundleService:
    def __init__(
        self,
        repository: FileConfigRepository,
        *,
        packages_dir: Path | Callable[[], Path],
        skills_dir: Path | Callable[[], Path],
        runtime_root: Path,
    ) -> None:
        self._repository = repository
        self._packages_dir_source = packages_dir
        self._skills_dir_source = skills_dir
        self._runtime_root = runtime_root
        self._lock = threading.RLock()

    @property
    def _packages_dir(self) -> Path:
        value = self._packages_dir_source() if callable(self._packages_dir_source) else self._packages_dir_source
        return Path(value).resolve()

    @property
    def _skills_dir(self) -> Path:
        value = self._skills_dir_source() if callable(self._skills_dir_source) else self._skills_dir_source
        return Path(value).resolve()

    def _exporter(self) -> ConfigurationBundleExporter:
        return ConfigurationBundleExporter(
            self._repository,
            packages_dir=self._packages_dir,
            skills_dir=self._skills_dir,
            runtime_root=self._runtime_root,
        )

    def _planner(self) -> BundleImportPlanner:
        return BundleImportPlanner(
            self._repository,
            packages_dir=self._packages_dir,
            skills_dir=self._skills_dir,
            runtime_root=self._runtime_root,
        )

    def export(self, root: BundleRoot) -> ExportedBundle:
        with self._lock:
            with self._repository.exclusive_config_mutation():
                return self._exporter().export(root)

    def preview(self, content: bytes) -> dict[str, object]:
        with self._lock:
            with self._repository.exclusive_config_mutation():
                return self._planner().preview(content).public_plan

    def commit(
        self,
        content: bytes,
        *,
        bundle_sha256: str,
        resolutions: ImportResolutions,
    ) -> dict[str, object]:
        with self._lock:
            with self._repository.exclusive_config_mutation():
                prepared = self._planner().prepare(
                    content,
                    resolutions=resolutions,
                    require_resolved=True,
                )
                if prepared.parsed.bundle_sha256 != bundle_sha256:
                    raise BundleImportError(
                        "import bundle digest does not match the previewed bundle"
                    )
                errors = prepared.public_plan["errors"]
                if errors or prepared.public_plan["ready"] is not True:
                    raise BundleImportError(
                        "configuration bundle import has unresolved blocking issues",
                        issues=list(errors) if isinstance(errors, list) else [],
                    )
                return commit_prepared_import(
                    self._repository,
                    prepared,
                    packages_dir=self._packages_dir,
                    skills_dir=self._skills_dir,
                    runtime_root=self._runtime_root,
                )


__all__ = ["ConfigurationBundleService"]
