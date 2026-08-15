from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path
from typing import Any, Callable

from agent_shell.python_packages.loader import PythonPackageLoader
from agent_shell.python_packages.config import validate_python_package_config
from agent_shell.python_packages.packages import (
    resolve_python_package,
    scan_python_package,
    scan_python_packages,
)
from agent_shell.runtime.errors import AgentRuntimeError


_FAMILY = "workflow-node"
_ADAPTER = "condition-router"
_FACTORY = "create_router"
_PARAMETERS = ("config",)


def scan_condition_router_package(
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


def resolve_condition_router_package(
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


def scan_condition_router_packages(
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


class ConditionRouterPackageRuntime:
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
        self._routers: dict[str, Callable[..., Any]] = {}
        self._closed = False

    def router_for(
        self,
        owner_id: str,
        bindings: list[dict[str, Any]],
    ) -> Callable[..., Any]:
        cached = self._routers.get(owner_id)
        if cached is not None:
            return cached
        enabled = [binding for binding in bindings if binding.get("enabled", True)]
        if len(enabled) != 1:
            raise AgentRuntimeError(
                "condition_router_package.binding_required",
                "Condition Router requires exactly one enabled Python package binding.",
                status_code=422,
            )
        binding = enabled[0]
        package_id = str(binding["package_id"])
        factory, metadata, _package_dir = self._loader.entrypoint(
            owner_id,
            "condition-router",
            0,
            package_id,
        )
        config = deepcopy(dict(binding.get("config", {})))
        if validate_python_package_config(metadata["config_schema"], config):
            raise AgentRuntimeError(
                "python_package.config_invalid",
                f"Python package {package_id!r} configuration is invalid.",
                status_code=422,
            )
        try:
            route = factory(config)
        except Exception as exc:
            raise AgentRuntimeError(
                "condition_router_package.materialization_failed",
                f"Condition Router package {package_id!r} could not create a router.",
                status_code=422,
            ) from exc
        if not callable(route) or not inspect.iscoroutinefunction(route):
            raise AgentRuntimeError(
                "condition_router_package.result_invalid",
                f"Condition Router package {package_id!r} must return an async route callable.",
                status_code=422,
            )
        try:
            signature = inspect.signature(route)
        except (TypeError, ValueError) as exc:
            raise AgentRuntimeError(
                "condition_router_package.result_invalid",
                f"Condition Router package {package_id!r} returned an invalid route callable.",
                status_code=422,
            ) from exc
        parameters = list(signature.parameters.values())
        if (
            [parameter.name for parameter in parameters] != ["state", "context"]
            or any(
                parameter.kind is not parameter.POSITIONAL_OR_KEYWORD
                or parameter.default is not parameter.empty
                for parameter in parameters
            )
        ):
            raise AgentRuntimeError(
                "condition_router_package.result_invalid",
                f"Condition Router package {package_id!r} route must accept exactly state and context.",
                status_code=422,
            )
        self._routers[owner_id] = route
        return route

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loader.close()
        self._routers.clear()


__all__ = [
    "ConditionRouterPackageRuntime",
    "resolve_condition_router_package",
    "scan_condition_router_package",
    "scan_condition_router_packages",
]
