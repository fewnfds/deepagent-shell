from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import sys
from types import MappingProxyType, ModuleType, SimpleNamespace
from typing import Any
from uuid import uuid4

from agent_shell.automation.scripts import resolve_automation_script
from agent_shell.registries.errors import ResourceScanError
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.validation.service import StaticAssembly


_LOGGER = logging.getLogger("agent_shell.automation")
_MAX_VARIABLE_BYTES = 256 * 1024


def _json_value(value: Any) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("automation variables must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > _MAX_VARIABLE_BYTES:
        raise ValueError("an automation variable may not exceed 256 KiB")
    return json.loads(encoded)


class AutomationVariables:
    def __init__(
        self,
        request_values: dict[str, Any],
        agent_values: dict[str, Any],
        workflow_values: dict[str, Any],
    ) -> None:
        self._scopes = {
            "request": request_values,
            "agent": agent_values,
            "workflow": workflow_values,
        }

    @staticmethod
    def _split(path: str) -> tuple[str, str]:
        scope, separator, key = path.partition(".")
        if not separator or scope not in {"request", "agent", "workflow"} or not key:
            raise ValueError(
                "variable paths must use request.<key>, agent.<key>, or workflow.<key>"
            )
        return scope, key

    def get(self, path: str, default: Any = None) -> Any:
        scope, key = self._split(path)
        return deepcopy(self._scopes[scope].get(key, default))

    def set(self, path: str, value: Any) -> None:
        scope, key = self._split(path)
        self._scopes[scope][key] = _json_value(value)

    def delete(self, path: str) -> None:
        scope, key = self._split(path)
        self._scopes[scope].pop(key, None)


@dataclass(frozen=True, slots=True)
class AutomationOwner:
    id: str
    type: str
    name: str
    hook_workflow: dict[str, Any] | None
    lifecycle_workflow: dict[str, Any] | None
    mapped_paths: Mapping[str, Path]


@dataclass(frozen=True, slots=True)
class _NodeKey:
    owner_id: str
    workflow_type: str
    workflow_id: str
    hook: str
    index: int


def _is_link(path: Path) -> bool:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _copy_plain_tree(source: Path, destination: Path) -> None:
    if _is_link(source) or not source.is_dir():
        raise ValueError("Skill sources must be ordinary directories")
    destination.mkdir(parents=True, exist_ok=False)
    with os.scandir(source) as entries:
        for entry in entries:
            source_path = Path(entry.path)
            if _is_link(source_path):
                raise ValueError("Skill overlays do not support links or reparse points")
            destination_path = destination / entry.name
            if entry.is_dir(follow_symlinks=False):
                _copy_plain_tree(source_path, destination_path)
            elif entry.is_file(follow_symlinks=False):
                shutil.copy2(source_path, destination_path)


class AutomationContext:
    def __init__(
        self,
        *,
        runtime: "AutomationRuntime",
        owner: AutomationOwner,
        workflow_type: str,
        workflow: dict[str, Any],
        node: dict[str, Any],
        plugin_dir: Path,
        variables: AutomationVariables,
        hook: str,
        tick: int | None,
        messages: list[dict[str, str]] | None,
        initial_files: dict[str, str | bytes] | None,
        terminal: Mapping[str, Any] | None,
    ) -> None:
        self.config = MappingProxyType(deepcopy(dict(node.get("config", {}))))
        self.vars = variables
        self.messages = messages
        self.initial_files = initial_files
        self.request = MappingProxyType({"id": runtime.request_id})
        self.agent = MappingProxyType(
            {"id": owner.id, "type": owner.type, "name": owner.name}
        )
        self.workflow = MappingProxyType(
            {
                "id": str(workflow.get("id", "")),
                "type": workflow_type,
                "name": str(workflow.get("name", "")),
            }
        )
        self.node = MappingProxyType(
            {"script_id": str(node.get("script_id", "")), "hook": hook}
        )
        self.tick = tick
        self.terminal = terminal
        self.paths = SimpleNamespace(
            plugin_dir=plugin_dir,
            runtime_dir=runtime.owner_runtime_dir(owner.id),
            mapped=owner.mapped_paths,
        )
        self._runtime = runtime
        self._owner_id = owner.id
        self._hook = hook
        self._graph_stop_requested = False

    def prepare_skill(self, name: str, mode: str = "overlay") -> Path:
        if self._hook != "request_prepare":
            raise ValueError("Skills may only be prepared during request_prepare")
        return self._runtime.prepare_skill(self._owner_id, name, mode=mode)

    def request_graph_stop(self) -> None:
        if self._hook == "request_end":
            raise ValueError("The Agent graph has already stopped during request_end")
        self._graph_stop_requested = True

    def log(self, message: object) -> None:
        _LOGGER.info(
            "automation request=%s agent=%s workflow=%s script=%s: %s",
            self.request["id"],
            self.agent["id"],
            self.workflow["id"],
            self.node["script_id"],
            str(message)[:2000],
        )


class AutomationRuntime:
    """Request-local owner state and execution outside the Agent graph."""

    def __init__(
        self,
        *,
        request_id: str,
        owners: list[AutomationOwner],
        client_messages: list[dict[str, str]],
        scripts_dir: Path,
        skills_dir: Path,
        runtime_root: Path,
    ) -> None:
        self.request_id = request_id or str(uuid4())
        self._owners = owners
        self._owner_by_id = {owner.id: owner for owner in owners}
        self._messages = {
            owner.id: [dict(message) for message in client_messages] for owner in owners
        }
        self._initial_files: dict[str, dict[str, str | bytes]] = {
            owner.id: {} for owner in owners
        }
        self._request_variables: dict[str, Any] = {}
        self._agent_variables: dict[str, dict[str, Any]] = {
            owner.id: {} for owner in owners
        }
        self._workflow_variables: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._scripts_dir = scripts_dir
        self._skills_dir = skills_dir
        self._request_runtime_dir = (
            runtime_root / "automation" / self.request_id
        ).resolve()
        self._modules: dict[_NodeKey, tuple[ModuleType, Callable[[Any], Any], Path]] = {}
        self._module_names: set[str] = set()
        self._overlay_owners: set[str] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._graph_stop_event = asyncio.Event()
        self._started = False
        self._closed = False

    @classmethod
    def from_assembly(
        cls,
        assembly: StaticAssembly,
        client_messages: list[dict[str, str]],
        *,
        primary_id: str,
        request_id: str,
        scripts_dir: Path,
        skills_dir: Path,
        runtime_root: Path,
    ) -> "AutomationRuntime":
        owners: list[AutomationOwner] = []

        def mapped_paths(blocks: dict[str, dict[str, Any]]) -> Mapping[str, Path]:
            filesystem = blocks.get("filesystem", {})
            values = {
                str(item["virtual_path"]): Path(str(item["local_path"])).resolve()
                for item in filesystem.get("mapped_directories", [])
            }
            return MappingProxyType(values)

        owners.append(
            AutomationOwner(
                id=primary_id,
                type="primary",
                name=str(assembly.primary.get("name", "")),
                hook_workflow=assembly.hook_workflow,
                lifecycle_workflow=assembly.lifecycle_workflow,
                mapped_paths=mapped_paths(assembly.blocks),
            )
        )
        seen: set[str] = set()

        def visit(edge: Any) -> None:
            key = str(edge.target_key)
            if key in seen:
                return
            seen.add(key)
            node = assembly.subagent_nodes[key]
            owners.append(
                AutomationOwner(
                    id=node.key,
                    type="subagent",
                    name=node.name,
                    hook_workflow=node.hook_workflow,
                    lifecycle_workflow=node.lifecycle_workflow,
                    mapped_paths=mapped_paths(node.blocks),
                )
            )
            for child in node.subagents:
                visit(child)

        for root in assembly.subagents:
            visit(root)
        return cls(
            request_id=request_id,
            owners=owners,
            client_messages=client_messages,
            scripts_dir=scripts_dir,
            skills_dir=skills_dir,
            runtime_root=runtime_root,
        )

    def owner_runtime_dir(self, owner_id: str) -> Path:
        path = self._request_runtime_dir / owner_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def prepare_skill(self, owner_id: str, name: str, *, mode: str) -> Path:
        if not name or Path(name).name != name:
            raise ValueError("Skill names must be one directory name")
        source = self._skills_dir / name
        if not source.is_dir():
            raise ValueError(f"Skill {name!r} does not exist")
        if mode == "persistent":
            if _is_link(source):
                raise ValueError("Skill folders may not be links or reparse points")
            return source
        if mode != "overlay":
            raise ValueError("Skill mode must be 'persistent' or 'overlay'")
        overlay_root = self.owner_runtime_dir(owner_id) / "skills"
        overlay = overlay_root / name
        if not overlay.exists():
            overlay_root.mkdir(parents=True, exist_ok=True)
            _copy_plain_tree(source, overlay)
        self._overlay_owners.add(owner_id)
        return overlay

    def effective_skills_dir(self, owner_id: str, selected: list[str]) -> Path:
        if owner_id not in self._overlay_owners:
            return self._skills_dir
        overlay_root = self.owner_runtime_dir(owner_id) / "skills"
        for name in selected:
            overlay = overlay_root / name
            if not overlay.exists():
                _copy_plain_tree(self._skills_dir / name, overlay)
        return overlay_root

    def messages_for(self, owner_id: str) -> list[dict[str, str]]:
        return [dict(message) for message in self._messages[owner_id]]

    def initial_files_for(self, owner_id: str) -> dict[str, str | bytes]:
        return dict(self._initial_files[owner_id])

    async def prepare(self) -> None:
        for owner in self._owners:
            if owner.hook_workflow is None:
                continue
            await self._run_hook(
                owner,
                owner.hook_workflow,
                "request_prepare",
                messages=self._messages[owner.id],
                initial_files=self._initial_files[owner.id],
            )
            if self.graph_stop_requested:
                raise self.graph_stop_error()

    async def before_subagent_invoke(
        self,
        owner_id: str,
        delegated_messages: list[Any],
    ) -> list[Any]:
        owner = self._owner_by_id[owner_id]
        messages = self.messages_for(owner_id)
        if owner.hook_workflow is not None:
            await self._run_hook(
                owner,
                owner.hook_workflow,
                "subagent_before_invoke",
                messages=messages,
            )
        from agent_shell.runtime.agent_builder import validate_openai_messages

        messages = validate_openai_messages(messages)
        return [*messages, *delegated_messages]

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self._stop_event.is_set():
            return
        for owner in self._owners:
            if owner.lifecycle_workflow is not None:
                self._tasks.append(
                    asyncio.create_task(
                        self._lifecycle_loop(owner, owner.lifecycle_workflow),
                        name=f"automation:{self.request_id}:{owner.id}",
                    )
                )
        if self._tasks:
            await asyncio.sleep(0)

    async def finish(self, terminal: Mapping[str, Any]) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for owner in self._owners:
            if owner.hook_workflow is None:
                continue
            try:
                await self._run_hook(
                    owner,
                    owner.hook_workflow,
                    "request_end",
                    terminal=terminal,
                )
            except Exception:
                _LOGGER.exception(
                    "request_end automation failed request=%s agent=%s",
                    self.request_id,
                    owner.id,
                )
        for module_name in self._module_names:
            for loaded_name in tuple(sys.modules):
                if loaded_name == module_name or loaded_name.startswith(
                    f"{module_name}."
                ):
                    sys.modules.pop(loaded_name, None)
        if self._request_runtime_dir.exists():
            shutil.rmtree(self._request_runtime_dir, ignore_errors=True)

    @property
    def graph_stop_requested(self) -> bool:
        return self._graph_stop_event.is_set()

    async def wait_for_graph_stop(self) -> None:
        await self._graph_stop_event.wait()

    @staticmethod
    def graph_stop_error() -> AgentRuntimeError:
        return AgentRuntimeError(
            "automation_requested_graph_stop",
            "An automation script requested that the Agent graph stop.",
            status_code=409,
        )

    def _request_graph_stop(self) -> None:
        self._graph_stop_event.set()
        self._stop_event.set()

    async def _lifecycle_loop(
        self, owner: AutomationOwner, workflow: dict[str, Any]
    ) -> None:
        tick = 0
        interval = float(workflow["interval_seconds"])
        while not self._stop_event.is_set():
            try:
                await self._run_nodes(
                    owner,
                    "lifecycle-workflow",
                    workflow,
                    list(workflow["nodes"]),
                    hook="lifecycle",
                    tick=tick,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception(
                    "lifecycle automation stopped request=%s agent=%s workflow=%s",
                    self.request_id,
                    owner.id,
                    workflow.get("id", ""),
                )
                return
            tick += 1
            if self._stop_event.is_set():
                return
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def _run_hook(
        self,
        owner: AutomationOwner,
        workflow: dict[str, Any],
        hook: str,
        *,
        messages: list[dict[str, str]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        await self._run_nodes(
            owner,
            "hook-workflow",
            workflow,
            list(workflow["hooks"].get(hook, [])),
            hook=hook,
            messages=messages,
            initial_files=initial_files,
            terminal=terminal,
        )

    async def _run_nodes(
        self,
        owner: AutomationOwner,
        workflow_type: str,
        workflow: dict[str, Any],
        nodes: list[dict[str, Any]],
        *,
        hook: str,
        tick: int | None = None,
        messages: list[dict[str, str]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        workflow_id = str(workflow.get("id", ""))
        variables = AutomationVariables(
            self._request_variables,
            self._agent_variables[owner.id],
            self._workflow_variables.setdefault(
                (owner.id, workflow_type, workflow_id), {}
            ),
        )
        for index, node in enumerate(nodes):
            key = _NodeKey(owner.id, workflow_type, workflow_id, hook, index)
            run, plugin_dir = self._load_node(key, str(node["script_id"]))
            context = AutomationContext(
                runtime=self,
                owner=owner,
                workflow_type=workflow_type,
                workflow=workflow,
                node=node,
                plugin_dir=plugin_dir,
                variables=variables,
                hook=hook,
                tick=tick,
                messages=messages,
                initial_files=initial_files,
                terminal=terminal,
            )
            try:
                await run(context)
                if context._graph_stop_requested:
                    self._request_graph_stop()
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise AgentRuntimeError(
                    "automation_script_failed",
                    (
                        f"Automation script {node['script_id']!r} failed for "
                        f"Agent {owner.name!r}."
                    ),
                    status_code=422,
                ) from exc

    def _load_node(
        self, key: _NodeKey, script_id: str
    ) -> tuple[Callable[[Any], Any], Path]:
        cached = self._modules.get(key)
        if cached is not None:
            return cached[1], cached[2]
        try:
            resolved = resolve_automation_script(script_id, self._scripts_dir)
        except ResourceScanError as exc:
            raise AgentRuntimeError(
                "automation_script_invalid",
                f"Automation script {script_id!r} is invalid.",
                status_code=422,
            ) from exc
        if resolved is None:
            raise AgentRuntimeError(
                "automation_script_not_found",
                f"Automation script {script_id!r} does not exist.",
                status_code=422,
            )
        _metadata, plugin_dir = resolved
        module_name = (
            "_agent_shell_automation_"
            f"{self.request_id.replace('-', '_')}_{len(self._modules)}"
        )
        spec = importlib.util.spec_from_file_location(
            module_name,
            plugin_dir / "main.py",
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec is None or spec.loader is None:
            raise AgentRuntimeError(
                "automation_script_load_failed",
                f"Automation script {script_id!r} could not be loaded.",
                status_code=422,
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            for loaded_name in tuple(sys.modules):
                if loaded_name == module_name or loaded_name.startswith(
                    f"{module_name}."
                ):
                    sys.modules.pop(loaded_name, None)
            raise AgentRuntimeError(
                "automation_script_load_failed",
                f"Automation script {script_id!r} could not be loaded.",
                status_code=422,
            ) from exc
        run = getattr(module, "run", None)
        if not inspect.iscoroutinefunction(run):
            raise AgentRuntimeError(
                "automation_script_entrypoint_invalid",
                f"Automation script {script_id!r} must expose async def run(ctx).",
                status_code=422,
            )
        self._modules[key] = (module, run, plugin_dir)
        self._module_names.add(module_name)
        return run, plugin_dir
