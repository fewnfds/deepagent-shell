from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable

from agent_shell.automation.scripts import resolve_automation_script
from agent_shell.registries.errors import ResourceScanError
from agent_shell.runtime.errors import AgentRuntimeError


class AutomationPluginLoader:
    def __init__(
        self,
        *,
        request_id: str,
        plugins_dir: Path,
        runtime_root: Path,
    ) -> None:
        self._request_id = request_id
        self._plugins_dir = plugins_dir
        self._runtime_root = runtime_root
        self._modules: dict[tuple[str, int], tuple[ModuleType, dict[str, object], Path]] = {}
        self._module_names: set[str] = set()

    def load(
        self,
        owner_id: str,
        binding_index: int,
        plugin_id: str,
    ) -> tuple[ModuleType, dict[str, object], Path]:
        key = (owner_id, binding_index)
        cached = self._modules.get(key)
        if cached is not None:
            return cached
        try:
            resolved = resolve_automation_script(
                plugin_id,
                self._plugins_dir,
                runtime_root=self._runtime_root,
            )
        except ResourceScanError as exc:
            raise AgentRuntimeError(
                "automation_plugin_invalid",
                f"Automation plugin {plugin_id!r} is invalid.",
                status_code=422,
            ) from exc
        if resolved is None:
            raise AgentRuntimeError(
                "automation_plugin_not_found",
                f"Automation plugin {plugin_id!r} does not exist.",
                status_code=422,
            )
        metadata, plugin_dir = resolved
        if metadata["dependency_status"] != "ready":
            raise AgentRuntimeError(
                "automation_plugin_dependencies_not_ready",
                f"Automation plugin {plugin_id!r} dependencies are not ready.",
                status_code=409,
            )
        module_name = (
            "_agent_shell_automation_"
            f"{self._request_id.replace('-', '_')}_{len(self._modules)}"
        )
        spec = importlib.util.spec_from_file_location(
            module_name,
            plugin_dir / "main.py",
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            raise AgentRuntimeError(
                "automation_plugin_load_failed",
                f"Automation plugin {plugin_id!r} could not be loaded.",
                status_code=422,
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            self._remove_module(module_name)
            raise AgentRuntimeError(
                "automation_plugin_load_failed",
                f"Automation plugin {plugin_id!r} could not be loaded.",
                status_code=422,
            ) from exc
        value = (module, metadata, plugin_dir)
        self._modules[key] = value
        self._module_names.add(module_name)
        return value

    def entrypoint(
        self,
        owner_id: str,
        binding_index: int,
        plugin_id: str,
        name: str,
    ) -> tuple[Callable[[Any], Any] | None, Path]:
        module, metadata, plugin_dir = self.load(owner_id, binding_index, plugin_id)
        if name not in metadata["entrypoints"]:
            return None, plugin_dir
        function_name = "create_middleware" if name == "middleware" else name
        function = getattr(module, function_name, None)
        expected_async = name != "middleware"
        if not callable(function) or inspect.iscoroutinefunction(function) != expected_async:
            raise AgentRuntimeError(
                "automation_plugin_entrypoint_invalid",
                f"Automation plugin {plugin_id!r} has an invalid {name} entrypoint.",
                status_code=422,
            )
        return function, plugin_dir

    @staticmethod
    def _remove_module(module_name: str) -> None:
        for loaded_name in tuple(sys.modules):
            if loaded_name == module_name or loaded_name.startswith(f"{module_name}."):
                sys.modules.pop(loaded_name, None)

    def close(self) -> None:
        for module_name in self._module_names:
            self._remove_module(module_name)
        self._modules.clear()
        self._module_names.clear()
