from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import uuid4

from agent_shell.python_packages.contracts import (
    EMPTY_TEMPLATE_KEY,
    validate_package_relative_path,
)
from agent_shell.python_packages.packages import (
    PythonPackageManifest,
    inspect_python_package_draft,
    resolve_python_package,
    resolve_owned_python_package_folder,
    scan_python_package,
    scan_python_package_template,
    scan_python_package_templates,
)
from agent_shell.registries.errors import ResourceScanError


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PackageAdapterSpec:
    template_parts: tuple[str, str]
    example_parts: tuple[str, str]
    family: str
    adapter: str
    factory_name: str
    factory_parameters: tuple[str, ...] | None


PACKAGE_COMPONENT_SPECS: dict[str, PackageAdapterSpec] = {
    "condition-router": PackageAdapterSpec(
        template_parts=("workflow", "condition_router"),
        example_parts=("workflow-components", "condition-router"),
        family="workflow-node",
        adapter="condition-router",
        factory_name="create_router",
        factory_parameters=(),
    ),
    "custom-middleware": PackageAdapterSpec(
        template_parts=("agent", "custom_middleware"),
        example_parts=("agent-components", "custom-middleware"),
        family="middleware",
        adapter="agent-middleware",
        factory_name="create_middleware",
        factory_parameters=None,
    ),
}


BUILTIN_EXAMPLE_TEMPLATE_PREFIX = "内置示例-"


class PythonPackageAuthoringError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(slots=True)
class PackageChange:
    rollback_callback: Any
    finalize_callback: Any = None

    def rollback(self) -> None:
        self.rollback_callback()

    def finalize(self) -> None:
        if self.finalize_callback is not None:
            self.finalize_callback()


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _restore_file(path: Path, existed: bool, content: bytes) -> None:
    if existed:
        _write_bytes_atomic(path, content)
    else:
        path.unlink(missing_ok=True)


def _file_entries(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > 50:
        raise PythonPackageAuthoringError(
            "python_package_files_invalid",
            "At least one editable Python package file is required.",
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if (
            not isinstance(item, dict)
            or not {"path", "content"}.issubset(item)
            or set(item) - {"path", "content", "exists", "readable"}
        ):
            raise PythonPackageAuthoringError(
                "python_package_files_invalid",
                "Each editable Python package file must contain path and content.",
            )
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise PythonPackageAuthoringError(
                "python_package_files_invalid",
                "Editable Python package paths and contents must be strings.",
            )
        try:
            validate_package_relative_path(path)
        except ValueError as exc:
            raise PythonPackageAuthoringError(
                "python_package_file_path_invalid",
                str(exc),
            ) from exc
        if path in seen:
            raise PythonPackageAuthoringError(
                "python_package_files_invalid",
                "Editable Python package file paths must be unique.",
            )
        seen.add(path)
        result.append({"path": path, "content": content})
    return result


def _editable_paths(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 50
        or not all(isinstance(path, str) for path in value)
    ):
        raise PythonPackageAuthoringError(
            "python_package_files_invalid",
            "Provide between 1 and 50 editable Python package file paths.",
        )
    paths = list(value)
    if len(paths) != len(set(paths)):
        raise PythonPackageAuthoringError(
            "python_package_files_invalid",
            "Editable Python package file paths must be unique.",
        )
    for path in paths:
        try:
            validate_package_relative_path(path)
        except ValueError as exc:
            raise PythonPackageAuthoringError(
                "python_package_file_path_invalid",
                str(exc),
            ) from exc
    return paths


def _read_editable_files(folder: Path, paths: list[str]) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path_value in paths:
        try:
            path = validate_package_relative_path(path_value)
        except ValueError:
            files.append({"path": path_value, "content": "", "exists": False, "readable": True})
            continue
        target = folder / Path(*path.split("/"))
        if not target.is_file():
            files.append({"path": path, "content": "", "exists": False, "readable": True})
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            files.append({"path": path, "content": "", "exists": True, "readable": False})
            continue
        files.append(
            {
                "path": path,
                "content": content.replace("\r\n", "\n").replace("\r", "\n"),
                "exists": True,
                "readable": True,
            }
        )
    return files


def _write_editable_files(folder: Path, entries: list[dict[str, str]]) -> None:
    for item in entries:
        target = folder / Path(*item["path"].split("/"))
        if target.is_dir():
            raise ResourceScanError(
                "resource.error.pythonPackage.readFailed",
                f"{item['path']} is a directory, not a text file.",
            )
        if not target.exists() and item["content"] == "":
            continue
        if target.is_file() and item["content"] == "":
            try:
                target.read_text(encoding="utf-8")
            except UnicodeError:
                continue
        _write_bytes_atomic(
            target,
            item["content"].replace("\r\n", "\n").encode("utf-8"),
        )


class PythonPackageAuthoringService:
    def __init__(
        self,
        *,
        templates_root: Path,
        examples_root: Path,
        instances_root: Path,
        runtime_root: Path,
    ) -> None:
        self._templates_root = templates_root
        self._examples_root = examples_root
        self._instances_root = instances_root
        self._runtime_root = runtime_root

    @staticmethod
    def supports(block_type: str) -> bool:
        return block_type in PACKAGE_COMPONENT_SPECS

    def _spec(self, block_type: str) -> PackageAdapterSpec:
        try:
            return PACKAGE_COMPONENT_SPECS[block_type]
        except KeyError as exc:
            raise PythonPackageAuthoringError(
                "python_package_component_unsupported",
                "The component type does not support a Python extension.",
            ) from exc

    def _template_root(self, spec: PackageAdapterSpec) -> Path:
        return self._templates_root.joinpath(*spec.template_parts)

    def _example_root(self, spec: PackageAdapterSpec) -> Path:
        return self._examples_root.joinpath(*spec.example_parts)

    def _adapter_root(self, spec: PackageAdapterSpec) -> Path:
        return self._instances_root / spec.adapter

    def template_catalog(self, block_type: str) -> dict[str, object]:
        spec = self._spec(block_type)
        templates = scan_python_package_templates(
            self._template_root(spec),
            family=spec.family,  # type: ignore[arg-type]
            adapter=spec.adapter,  # type: ignore[arg-type]
            factory_name=spec.factory_name,
            factory_parameters=spec.factory_parameters,
        )
        examples = scan_python_package_templates(
            self._example_root(spec),
            family=spec.family,  # type: ignore[arg-type]
            adapter=spec.adapter,  # type: ignore[arg-type]
            factory_name=spec.factory_name,
            factory_parameters=spec.factory_parameters,
        )
        example_catalog = []
        for item in examples["catalog"]:
            assert isinstance(item, dict)
            key = str(item["key"])
            example_catalog.append(
                {
                    **item,
                    "key": f"{BUILTIN_EXAMPLE_TEMPLATE_PREFIX}{key}",
                    "name": f"{BUILTIN_EXAMPLE_TEMPLATE_PREFIX}{item['name']}",
                }
            )
        example_errors = {
            f"{BUILTIN_EXAMPLE_TEMPLATE_PREFIX}{key}": value
            for key, value in examples["errors"].items()
        }
        return {
            "catalog": [*templates["catalog"], *example_catalog],
            "errors": {**templates["errors"], **example_errors},
        }

    def _scan_instance(
        self,
        block_type: str,
        owner_id: str,
        folder: str,
    ) -> tuple[dict[str, object], Path]:
        spec = self._spec(block_type)
        try:
            resolved = resolve_python_package(
                folder,
                self._instances_root,
                owner_id=owner_id,
                family=spec.family,  # type: ignore[arg-type]
                adapter=spec.adapter,  # type: ignore[arg-type]
                factory_name=spec.factory_name,
                factory_parameters=spec.factory_parameters,
                runtime_root=self._runtime_root,
            )
        except ResourceScanError as exc:
            raise PythonPackageAuthoringError(
                "python_package_invalid",
                "The configuration-owned Python extension is invalid.",
            ) from exc
        if resolved is None:
            raise PythonPackageAuthoringError(
                "python_package_not_found",
                "The Python extension directory is missing or is not owned by this configuration.",
                status_code=404,
            )
        return resolved

    def _inspect_instance(
        self,
        block_type: str,
        owner_id: str,
        folder_name: str,
    ) -> tuple[dict[str, object], Path]:
        spec = self._spec(block_type)
        folder = resolve_owned_python_package_folder(
            folder_name,
            self._instances_root,
            owner_id=owner_id,
            adapter=spec.adapter,  # type: ignore[arg-type]
        )
        if folder is None:
            raise PythonPackageAuthoringError(
                "python_package_not_found",
                "The Python extension directory is missing or is not owned by this configuration.",
                status_code=404,
            )
        try:
            return (
                inspect_python_package_draft(
                    folder,
                    owner_id=owner_id,
                    family=spec.family,  # type: ignore[arg-type]
                    adapter=spec.adapter,  # type: ignore[arg-type]
                    factory_name=spec.factory_name,
                    factory_parameters=spec.factory_parameters,
                    runtime_root=self._runtime_root,
                ),
                folder,
            )
        except ResourceScanError as exc:
            raise PythonPackageAuthoringError(
                "python_package_read_failed",
                f"The configuration-owned Python extension could not be inspected ({exc.message_key}).",
            ) from exc

    def project(
        self,
        block_type: str,
        owner_id: str,
        reference: dict[str, Any],
    ) -> dict[str, object]:
        inspection, folder = self._inspect_instance(
            block_type, owner_id, str(reference.get("folder", ""))
        )
        metadata = inspection["metadata"]
        assert metadata is None or isinstance(metadata, dict)
        package_error = inspection["error"]
        error_code = (
            str(package_error.get("message_key", "python_package_invalid"))
            if isinstance(package_error, dict)
            else ""
        )
        paths = reference.get("editable_files", ["main.py"])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            paths = ["main.py"]
        editable_files = _read_editable_files(folder, paths)
        return {
            "python_package_manifest": inspection["manifest"],
            "python_package_files": {
                "template_key": "",
                "files": editable_files,
                "revision": inspection["revision"],
            },
            "python_package_error": package_error,
            "requirements_fingerprint": (
                metadata["requirements_fingerprint"] if metadata is not None else ""
            ),
            "dependency_status": (
                metadata["dependency_status"] if metadata is not None else "failed"
            ),
            "dependency_error_code": (
                metadata["dependency_error_code"] if metadata is not None else error_code
            ),
        }

    def read_files(
        self,
        block_type: str,
        owner_id: str,
        reference: dict[str, Any],
        paths: object,
    ) -> dict[str, object]:
        requested_paths = _editable_paths(paths)
        inspection, folder = self._inspect_instance(
            block_type, owner_id, str(reference.get("folder", ""))
        )
        return {
            "template_key": "",
            "files": _read_editable_files(folder, requested_paths),
            "revision": inspection["revision"],
        }

    def create(
        self,
        block_type: str,
        owner_id: str,
        *,
        template_key: str,
        template_revision: str,
        files: list[dict[str, str]],
    ) -> tuple[dict[str, Any], PackageChange]:
        spec = self._spec(block_type)
        entries = _file_entries(files)
        template: Path | None = None
        if template_key != EMPTY_TEMPLATE_KEY:
            if template_key.startswith(BUILTIN_EXAMPLE_TEMPLATE_PREFIX):
                template_root = self._example_root(spec)
                folder_key = template_key.removeprefix(
                    BUILTIN_EXAMPLE_TEMPLATE_PREFIX
                )
            else:
                template_root = self._template_root(spec)
                folder_key = template_key
            template = template_root / folder_key
            if template.parent != template_root:
                raise PythonPackageAuthoringError(
                    "python_package_template_invalid",
                    "The selected Python package template key must name one template folder.",
                )
            try:
                metadata = scan_python_package_template(
                    template,
                    family=spec.family,  # type: ignore[arg-type]
                    adapter=spec.adapter,  # type: ignore[arg-type]
                    factory_name=spec.factory_name,
                    factory_parameters=spec.factory_parameters,
                )
            except ResourceScanError as exc:
                raise PythonPackageAuthoringError(
                    "python_package_template_invalid",
                    "The selected Python package template is invalid.",
                ) from exc
            if metadata["revision"] != template_revision:
                raise PythonPackageAuthoringError(
                    "python_package_template_revision_conflict",
                    "The Python package template changed after it was loaded.",
                    status_code=409,
                )
        elif template_revision:
            raise PythonPackageAuthoringError(
                "python_package_template_invalid",
                "The empty Python package template does not have a revision.",
            )
        folder_name = owner_id
        adapter_root = self._adapter_root(spec)
        adapter_root.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=".authoring-", dir=adapter_root))
        staged = staging_root / folder_name
        final = adapter_root / folder_name
        try:
            if template is not None:
                shutil.copytree(template, staged)
            else:
                staged.mkdir(parents=True)
            manifest = PythonPackageManifest.model_validate(
                {
                    "format_version": 1,
                    "id": owner_id,
                    "family": spec.family,
                    "adapter": spec.adapter,
                }
            )
            _write_bytes_atomic(
                staged / "package.json",
                (json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            _write_editable_files(staged, entries)
            scan_python_package(
                staged,
                owner_id=owner_id,
                family=spec.family,  # type: ignore[arg-type]
                adapter=spec.adapter,  # type: ignore[arg-type]
                factory_name=spec.factory_name,
                factory_parameters=spec.factory_parameters,
                runtime_root=self._runtime_root,
            )
            os.replace(staged, final)
        except ResourceScanError as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise PythonPackageAuthoringError(
                "python_package_invalid",
                "The Python extension does not satisfy its adapter contract.",
            ) from exc
        except BaseException:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise
        shutil.rmtree(staging_root, ignore_errors=True)
        return (
            {"folder": folder_name, "editable_files": [item["path"] for item in entries]},
            PackageChange(lambda: shutil.rmtree(final, ignore_errors=True)),
        )

    def update(
        self,
        block_type: str,
        owner_id: str,
        reference: dict[str, Any],
        *,
        revision: str,
        files: list[dict[str, str]],
    ) -> PackageChange:
        entries = _file_entries(files)
        inspection, folder = self._inspect_instance(
            block_type, owner_id, str(reference.get("folder", ""))
        )
        if inspection["revision"] != revision:
            raise PythonPackageAuthoringError(
                "python_package_revision_conflict",
                "The Python extension changed after it was loaded.",
                status_code=409,
            )
        spec = self._spec(block_type)
        staging_root = Path(tempfile.mkdtemp(prefix=".authoring-", dir=self._adapter_root(spec)))
        staged = staging_root / folder.name
        try:
            shutil.copytree(folder, staged)
            _write_editable_files(staged, entries)
            scan_python_package(
                staged,
                owner_id=owner_id,
                family=spec.family,  # type: ignore[arg-type]
                adapter=spec.adapter,  # type: ignore[arg-type]
                factory_name=spec.factory_name,
                factory_parameters=spec.factory_parameters,
                runtime_root=self._runtime_root,
            )
        except ResourceScanError as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise PythonPackageAuthoringError(
                "python_package_invalid",
                "The Python extension does not satisfy its adapter contract.",
            ) from exc
        except BaseException:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise

        snapshots: list[tuple[Path, bool, bytes]] = []
        for item in entries:
            target = folder / Path(*item["path"].split("/"))
            existed = target.is_file()
            snapshots.append((target, existed, target.read_bytes() if existed else b""))
        current, _ = self._inspect_instance(block_type, owner_id, folder.name)
        if current["revision"] != revision:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise PythonPackageAuthoringError(
                "python_package_revision_conflict",
                "The Python extension changed after it was loaded.",
                status_code=409,
            )
        try:
            _write_editable_files(folder, entries)
        except BaseException:
            for target, existed, content in snapshots:
                _restore_file(target, existed, content)
            shutil.rmtree(staging_root, ignore_errors=True)
            raise
        shutil.rmtree(staging_root, ignore_errors=True)

        def rollback() -> None:
            for target, existed, content in snapshots:
                _restore_file(target, existed, content)

        return PackageChange(rollback)

    def copy(
        self,
        block_type: str,
        source_owner_id: str,
        target_owner_id: str,
        reference: dict[str, Any],
    ) -> tuple[dict[str, Any], PackageChange]:
        _metadata, source = self._scan_instance(
            block_type, source_owner_id, str(reference.get("folder", ""))
        )
        spec = self._spec(block_type)
        folder_name = target_owner_id
        final = self._adapter_root(spec) / folder_name
        staging_root = Path(tempfile.mkdtemp(prefix=".authoring-", dir=self._adapter_root(spec)))
        staged = staging_root / folder_name
        try:
            shutil.copytree(source, staged)
            manifest_path = staged / "package.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["id"] = target_owner_id
            _write_bytes_atomic(
                manifest_path,
                (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            scan_python_package(
                staged,
                owner_id=target_owner_id,
                family=spec.family,  # type: ignore[arg-type]
                adapter=spec.adapter,  # type: ignore[arg-type]
                factory_name=spec.factory_name,
                factory_parameters=spec.factory_parameters,
                runtime_root=self._runtime_root,
            )
            os.replace(staged, final)
        except ResourceScanError as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise PythonPackageAuthoringError(
                "python_package_invalid",
                "The copied Python package does not satisfy its adapter contract.",
            ) from exc
        except BaseException:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise
        shutil.rmtree(staging_root, ignore_errors=True)
        paths = reference.get("editable_files", ["main.py"])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            paths = ["main.py"]
        return (
            {"folder": folder_name, "editable_files": list(paths)},
            PackageChange(lambda: shutil.rmtree(final, ignore_errors=True)),
        )

    def stage_delete(
        self,
        block_type: str,
        owner_id: str,
        reference: dict[str, Any],
    ) -> PackageChange:
        spec = self._spec(block_type)
        folder_name = str(reference.get("folder", ""))
        folder = resolve_owned_python_package_folder(
            folder_name,
            self._instances_root,
            owner_id=owner_id,
            adapter=spec.adapter,  # type: ignore[arg-type]
        )
        if folder is None:
            logger.warning(
                "Skipping Python extension cleanup: code=python_package_not_found owner_id=%s folder=%s",
                owner_id,
                folder_name,
            )
            return PackageChange(lambda: None)
        try:
            inspect_python_package_draft(
                folder,
                owner_id=owner_id,
                family=spec.family,  # type: ignore[arg-type]
                adapter=spec.adapter,  # type: ignore[arg-type]
                factory_name=spec.factory_name,
                factory_parameters=spec.factory_parameters,
                runtime_root=self._runtime_root,
            )
        except ResourceScanError as exc:
            logger.warning(
                "Skipping unsafe Python extension cleanup: code=%s owner_id=%s folder=%s",
                exc.message_key,
                owner_id,
                folder_name,
            )
            return PackageChange(lambda: None)
        tombstone_root = folder.parent / f".deleted-{uuid4()}"
        tombstone_root.mkdir(parents=True)
        tombstone = tombstone_root / folder.name
        os.replace(folder, tombstone)

        def rollback() -> None:
            folder.parent.mkdir(parents=True, exist_ok=True)
            if tombstone.exists():
                os.replace(tombstone, folder)
            shutil.rmtree(tombstone_root, ignore_errors=True)

        def finalize() -> None:
            shutil.rmtree(tombstone_root, ignore_errors=True)

        return PackageChange(rollback, finalize)


__all__ = [
    "BUILTIN_EXAMPLE_TEMPLATE_PREFIX",
    "PACKAGE_COMPONENT_SPECS",
    "PackageChange",
    "PythonPackageAuthoringError",
    "PythonPackageAuthoringService",
]
