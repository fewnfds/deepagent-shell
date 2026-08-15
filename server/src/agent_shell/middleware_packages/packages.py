from __future__ import annotations

from pathlib import Path

from agent_shell.python_packages.packages import (
    resolve_python_package,
    scan_python_package,
    scan_python_packages,
)


_FAMILY = "middleware"
_ADAPTER = "agent-middleware"
_FACTORY = "create_middleware"
_PARAMETERS = ("config", "agent")


def scan_middleware_package(
    folder: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    return scan_python_package(
        folder,
        family=_FAMILY,
        adapter=_ADAPTER,
        factory_name=_FACTORY,
        factory_parameters=_PARAMETERS,
        runtime_root=runtime_root,
    )


def resolve_middleware_package(
    package_id: str,
    directory: Path,
    *,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path] | None:
    return resolve_python_package(
        package_id,
        directory,
        family=_FAMILY,
        adapter=_ADAPTER,
        factory_name=_FACTORY,
        factory_parameters=_PARAMETERS,
        runtime_root=runtime_root,
    )


def scan_middleware_packages(
    directory: Path,
    *,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    return scan_python_packages(
        directory,
        family=_FAMILY,
        adapter=_ADAPTER,
        factory_name=_FACTORY,
        factory_parameters=_PARAMETERS,
        runtime_root=runtime_root,
    )


__all__ = [
    "resolve_middleware_package",
    "scan_middleware_package",
    "scan_middleware_packages",
]
