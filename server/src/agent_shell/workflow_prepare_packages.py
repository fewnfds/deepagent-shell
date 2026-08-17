from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from agent_shell.python_packages.loader import PythonPackageLoader
from agent_shell.python_packages.packages import resolve_python_package, scan_python_package
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.workflow_prepare import WorkflowPrepareCallable


_FAMILY = "workflow"
_ADAPTER = "workflow-prepare"
_FACTORY = "create_prepare"
_PARAMETERS: tuple[str, ...] = ()


def scan_workflow_prepare_package(
    folder: Path,
    *,
    owner_id: str,
    runtime_root: Path | None = None,
) -> dict[str, object]:
    return scan_python_package(
        folder,
        owner_id=owner_id,
        family=_FAMILY,
        adapter=_ADAPTER,
        factory_name=_FACTORY,
        factory_parameters=_PARAMETERS,
        runtime_root=runtime_root,
    )


def resolve_workflow_prepare_package(
    folder: str,
    directory: Path,
    *,
    owner_id: str,
    runtime_root: Path | None = None,
) -> tuple[dict[str, object], Path] | None:
    return resolve_python_package(
        folder,
        directory,
        owner_id=owner_id,
        family=_FAMILY,
        adapter=_ADAPTER,
        factory_name=_FACTORY,
        factory_parameters=_PARAMETERS,
        runtime_root=runtime_root,
    )


class WorkflowPreparePackageRuntime:
    def __init__(
        self,
        *,
        request_id: str,
        packages_dir: Path,
        runtime_root: Path,
    ) -> None:
        self._loader = PythonPackageLoader(
            request_id=request_id,
            packages_dir=packages_dir,
            runtime_root=runtime_root,
            family=_FAMILY,
            adapter=_ADAPTER,
            factory_name=_FACTORY,
            factory_parameters=_PARAMETERS,
        )
        self._closed = False

    def prepare_for(
        self,
        owner_id: str,
        reference: dict[str, Any],
    ) -> WorkflowPrepareCallable:
        folder = str(reference["folder"])
        factory, _metadata, _package_dir = self._loader.entrypoint(
            owner_id,
            "workflow-prepare",
            0,
            folder,
            package_owner_id=owner_id,
        )
        try:
            prepare = factory()
        except Exception as exc:
            raise AgentRuntimeError(
                "workflow_prepare_package.materialization_failed",
                f"Workflow Prepare package {folder!r} could not create a Prepare callable.",
                status_code=422,
            ) from exc
        if not callable(prepare) or not inspect.iscoroutinefunction(prepare):
            raise AgentRuntimeError(
                "workflow_prepare_package.result_invalid",
                f"Workflow Prepare package {folder!r} must return an async Prepare callable.",
                status_code=422,
            )
        try:
            signature = inspect.signature(prepare)
        except (TypeError, ValueError) as exc:
            raise AgentRuntimeError(
                "workflow_prepare_package.result_invalid",
                f"Workflow Prepare package {folder!r} returned an invalid callable.",
                status_code=422,
            ) from exc
        parameters = list(signature.parameters.values())
        if (
            [parameter.name for parameter in parameters] != ["input"]
            or any(
                parameter.kind is not parameter.POSITIONAL_OR_KEYWORD
                or parameter.default is not parameter.empty
                for parameter in parameters
            )
        ):
            raise AgentRuntimeError(
                "workflow_prepare_package.result_invalid",
                f"Workflow Prepare package {folder!r} callable must accept exactly input.",
                status_code=422,
            )
        return prepare

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loader.close()


__all__ = [
    "WorkflowPreparePackageRuntime",
    "resolve_workflow_prepare_package",
    "scan_workflow_prepare_package",
]
