from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Literal
from urllib.request import urlopen
from uuid import uuid4
from zipfile import ZipFile

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from agent_shell.registries.errors import ResourceScanError


DEPENDENCY_STATE_SCHEMA = 1
MAX_REQUIREMENTS_BYTES = 64 * 1024
MAX_REQUIREMENTS_COUNT = 100
PYPI_INDEX = "https://pypi.org/simple"
REQUIREMENTS_FILE = "requirements.txt"
RUNTIME_FOLDER = "middleware_packages"
SITE_PACKAGES_FOLDER = "site-packages"
STATE_FILE = "dependency-state.json"

DependencyStatus = Literal["ready", "restart_required", "failed"]


@dataclass(frozen=True, slots=True)
class PackageRequirements:
    values: tuple[str, ...]
    fingerprint: str


def _is_link(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _requirements_fingerprint(values: tuple[str, ...]) -> str:
    encoded = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def read_package_requirements(folder: Path) -> PackageRequirements:
    path = folder / REQUIREMENTS_FILE
    if not path.exists():
        values: tuple[str, ...] = ()
        return PackageRequirements(values, _requirements_fingerprint(values))
    if not path.is_file() or _is_link(path):
        raise ResourceScanError(
            "resource.error.middlewarePackage.requirementsLinkUnsupported",
            "requirements.txt must be an ordinary file.",
        )
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.requirementsReadFailed",
            "requirements.txt could not be read.",
        ) from exc
    if len(content) > MAX_REQUIREMENTS_BYTES:
        raise ResourceScanError(
            "resource.error.middlewarePackage.requirementsTooLarge",
            "requirements.txt may not exceed 64 KiB.",
        )
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise ResourceScanError(
            "resource.error.middlewarePackage.requirementsInvalidEncoding",
            "requirements.txt must use UTF-8 encoding.",
        ) from exc

    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-") or "\\" in line or "://" in line:
            raise ResourceScanError(
                "resource.error.middlewarePackage.requirementsInvalid",
                f"requirements.txt line {line_number} is not a package requirement.",
                {"line": line_number},
            )
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            raise ResourceScanError(
                "resource.error.middlewarePackage.requirementsInvalid",
                f"requirements.txt line {line_number} is invalid.",
                {"line": line_number},
            ) from exc
        if requirement.url is not None:
            raise ResourceScanError(
                "resource.error.middlewarePackage.requirementsInvalid",
                f"requirements.txt line {line_number} may not use a direct URL.",
                {"line": line_number},
            )
        name = canonicalize_name(requirement.name)
        if name in parsed:
            raise ResourceScanError(
                "resource.error.middlewarePackage.requirementsDuplicate",
                f"requirements.txt declares {requirement.name!r} more than once.",
                {"line": line_number, "package": requirement.name},
            )
        parsed[name] = str(requirement)
        if len(parsed) > MAX_REQUIREMENTS_COUNT:
            raise ResourceScanError(
                "resource.error.middlewarePackage.requirementsTooMany",
                "requirements.txt may contain at most 100 packages.",
            )

    values = tuple(parsed[name] for name in sorted(parsed))
    return PackageRequirements(values, _requirements_fingerprint(values))


def package_runtime_root(runtime_root: Path) -> Path:
    return runtime_root / RUNTIME_FOLDER


def dependency_state_path(runtime_root: Path) -> Path:
    return package_runtime_root(runtime_root) / STATE_FILE


def package_site_packages(runtime_root: Path) -> Path:
    return package_runtime_root(runtime_root) / SITE_PACKAGES_FOLDER


def load_dependency_state(runtime_root: Path | None) -> dict[str, Any] | None:
    if runtime_root is None:
        return None
    path = dependency_state_path(runtime_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("schema") != DEPENDENCY_STATE_SCHEMA
        or value.get("status") not in {"ready", "failed"}
        or not isinstance(value.get("packages"), dict)
    ):
        return None
    return value


def dependency_metadata(
    script_id: str,
    requirements: PackageRequirements,
    runtime_root: Path | None,
) -> dict[str, object]:
    if not requirements.values:
        status: DependencyStatus = "ready"
        error_code = ""
    else:
        state = load_dependency_state(runtime_root)
        package_state = (
            state.get("packages", {}).get(script_id)
            if state is not None
            else None
        )
        if (
            isinstance(package_state, dict)
            and package_state.get("requirements_fingerprint")
            == requirements.fingerprint
            and package_state.get("status") in {"ready", "failed"}
        ):
            status = package_state["status"]
            error_code = str(package_state.get("error_code", ""))
        else:
            status = "restart_required"
            error_code = ""
    return {
        "python_requirements": list(requirements.values),
        "requirements_fingerprint": requirements.fingerprint,
        "dependency_status": status,
        "dependency_error_code": error_code,
    }


def activate_package_site(runtime_root: Path) -> None:
    state = load_dependency_state(runtime_root)
    site_packages = package_site_packages(runtime_root)
    if state is None or state.get("status") != "ready" or not site_packages.is_dir():
        return
    site_text = str(site_packages.resolve())
    if site_text not in sys.path:
        # Core site-packages stays first so packages cannot shadow locked core modules.
        sys.path.append(site_text)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=True, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _runtime_manifest(runtime_root: Path) -> dict[str, Any]:
    path = runtime_root / "app" / "runtime-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("The Windows runtime manifest is invalid.")
    return value


def _input_fingerprint(
    core_fingerprint: str,
    packages: list[dict[str, object]],
) -> str:
    payload = {
        "core": core_fingerprint,
        "packages": [
            [item["id"], item["requirements_fingerprint"]]
            for item in sorted(packages, key=lambda value: str(value["id"]))
            if item["python_requirements"]
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _package_states(
    packages: list[dict[str, object]],
    *,
    status: Literal["ready", "failed"],
    error_code: str = "",
) -> dict[str, dict[str, str]]:
    return {
        str(item["id"]): {
            "requirements_fingerprint": str(item["requirements_fingerprint"]),
            "status": status,
            "error_code": error_code,
        }
        for item in packages
        if item["python_requirements"]
    }


def _write_failure_state(
    runtime_root: Path,
    packages: list[dict[str, object]],
    *,
    input_fingerprint: str,
    core_fingerprint: str,
    error_code: str,
) -> None:
    _atomic_write_json(
        dependency_state_path(runtime_root),
        {
            "schema": DEPENDENCY_STATE_SCHEMA,
            "platform": "windows-x64",
            "status": "failed",
            "input_fingerprint": input_fingerprint,
            "core_fingerprint": core_fingerprint,
            "packages": _package_states(
                packages, status="failed", error_code=error_code
            ),
        },
    )


def _safe_extract_uv(archive: Path, destination: Path) -> Path:
    with ZipFile(archive) as bundle:
        members = bundle.infolist()
        for member in members:
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("The uv archive contains an unsafe path.")
        bundle.extractall(destination)
    candidates = list(destination.rglob("uv.exe"))
    if len(candidates) != 1:
        raise ValueError("The uv archive does not contain exactly one uv.exe.")
    return candidates[0]


def _ensure_uv(runtime_root: Path, manifest: dict[str, Any]) -> Path:
    bootstrap = runtime_root / "bootstrap"
    uv_path = bootstrap / "uv.exe"
    version_path = bootstrap / "uv-version.txt"
    expected_version = str(manifest.get("uv", ""))
    installed_version = (
        version_path.read_text(encoding="ascii").strip()
        if version_path.is_file()
        else ""
    )
    if uv_path.is_file() and installed_version == expected_version:
        return uv_path

    url = str(manifest.get("uv_url", ""))
    expected_hash = str(manifest.get("uv_sha256", "")).lower()
    if not expected_version or not url.startswith("https://") or len(expected_hash) != 64:
        raise ValueError("The Windows runtime manifest lacks the pinned uv download.")

    temporary_root = runtime_root / "tmp" / f"uv-middleware-{uuid4().hex}"
    archive = temporary_root / "uv.zip"
    extracted = temporary_root / "extract"
    temporary_root.mkdir(parents=True)
    extracted.mkdir()
    try:
        digest = sha256()
        total = 0
        with urlopen(url, timeout=60) as response, archive.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 128 * 1024 * 1024:
                    raise ValueError("The uv download exceeds 128 MiB.")
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest().lower() != expected_hash:
            raise ValueError("The uv download failed SHA-256 verification.")
        downloaded = _safe_extract_uv(archive, extracted)
        bootstrap.mkdir(parents=True, exist_ok=True)
        temporary_uv = bootstrap / f"uv.{uuid4().hex}.tmp"
        shutil.copy2(downloaded, temporary_uv)
        os.replace(temporary_uv, uv_path)
        version_path.write_text(expected_version, encoding="ascii")
        return uv_path
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def _core_constraints() -> tuple[str, ...]:
    values: dict[str, str] = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        if not name or not distribution.version:
            continue
        values[canonicalize_name(name)] = f"{name}=={distribution.version}"
    return tuple(values[name] for name in sorted(values))


def _replace_site_packages(runtime_root: Path, prepared: Path) -> None:
    target = package_site_packages(runtime_root)
    previous = target.parent / f"site-packages.previous.{uuid4().hex}"
    target.parent.mkdir(parents=True, exist_ok=True)
    had_target = target.is_dir()
    if had_target:
        os.replace(target, previous)
    try:
        os.replace(prepared, target)
    except BaseException:
        if had_target and not target.exists():
            os.replace(previous, target)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def _package_layout_is_supported(site_packages: Path) -> bool:
    for path in site_packages.rglob("*"):
        if _is_link(path):
            return False
    return not any(site_packages.glob("*.pth"))


def prepare_windows_dependencies(
    *,
    data_root: Path,
    runtime_root: Path,
) -> None:
    from agent_shell.middleware_packages.packages import scan_middleware_packages

    manifest = _runtime_manifest(runtime_root)
    core_fingerprint = str(manifest.get("build_fingerprint", ""))
    if not core_fingerprint:
        raise ValueError("The Windows runtime manifest lacks its build fingerprint.")
    catalog = scan_middleware_packages(
        data_root / "resources" / "custom_middlewares",
        runtime_root=None,
    )["catalog"]
    packages = [dict(item) for item in catalog]
    input_fingerprint = _input_fingerprint(core_fingerprint, packages)
    current = load_dependency_state(runtime_root)
    target = package_site_packages(runtime_root)
    if (
        current is not None
        and current.get("status") == "ready"
        and current.get("input_fingerprint") == input_fingerprint
        and target.is_dir()
    ):
        print("Middleware package dependencies are already current.")
        return

    requirements = [
        requirement
        for package in packages
        for requirement in package["python_requirements"]
    ]
    build_root = runtime_root / "tmp" / f"middleware-packages-{uuid4().hex}"
    prepared = build_root / SITE_PACKAGES_FOLDER
    prepared.mkdir(parents=True)
    try:
        if requirements:
            uv_path = _ensure_uv(runtime_root, manifest)
            requirements_path = build_root / "requirements.txt"
            constraints_path = build_root / "core-constraints.txt"
            requirements_path.write_text(
                "\n".join(str(value) for value in requirements) + "\n",
                encoding="utf-8",
            )
            constraints_path.write_text(
                "\n".join(_core_constraints()) + "\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            for name in tuple(environment):
                if name.upper().startswith(("UV_", "PIP_")):
                    environment.pop(name)
            environment["UV_CACHE_DIR"] = str(runtime_root / "cache" / "uv")
            result = subprocess.run(
                [
                    str(uv_path),
                    "pip",
                    "install",
                    "--target",
                    str(prepared),
                    "--python-version",
                    str(manifest.get("python", "")),
                    "--python-platform",
                    "x86_64-pc-windows-msvc",
                    "--only-binary",
                    ":all:",
                    "--no-config",
                    "--default-index",
                    PYPI_INDEX,
                    "--constraints",
                    str(constraints_path),
                    "--requirements",
                    str(requirements_path),
                    "--quiet",
                ],
                check=False,
                env=environment,
            )
            if result.returncode != 0:
                _write_failure_state(
                    runtime_root,
                    packages,
                    input_fingerprint=input_fingerprint,
                    core_fingerprint=core_fingerprint,
                    error_code="dependency_resolution_failed",
                )
                print(
                    "WARNING: Middleware package dependencies could not be resolved. "
                    "Agent Shell will start without the package dependency layer.",
                    file=sys.stderr,
                )
                return
            if not _package_layout_is_supported(prepared):
                _write_failure_state(
                    runtime_root,
                    packages,
                    input_fingerprint=input_fingerprint,
                    core_fingerprint=core_fingerprint,
                    error_code="dependency_layout_unsupported",
                )
                print(
                    "WARNING: Middleware package dependencies contain unsupported "
                    "links or Python path files. Agent Shell will start without the "
                    "package dependency layer.",
                    file=sys.stderr,
                )
                return

        _replace_site_packages(runtime_root, prepared)
        _atomic_write_json(
            dependency_state_path(runtime_root),
            {
                "schema": DEPENDENCY_STATE_SCHEMA,
                "platform": "windows-x64",
                "status": "ready",
                "input_fingerprint": input_fingerprint,
                "core_fingerprint": core_fingerprint,
                "packages": _package_states(packages, status="ready"),
            },
        )
        print("Middleware package dependencies are ready.")
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agent_shell.middleware_packages.dependencies"
    )
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--data-dir", type=Path)
    parsed = parser.parse_args(arguments)
    home = parsed.home.resolve()
    data_root = parsed.data_dir or (home / "data")
    data_root = (
        data_root.resolve()
        if data_root.is_absolute()
        else (home / data_root).resolve()
    )
    try:
        prepare_windows_dependencies(
            data_root=data_root,
            runtime_root=(home / "runtime").resolve(),
        )
    except Exception as exc:
        print(f"Middleware package dependency preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
