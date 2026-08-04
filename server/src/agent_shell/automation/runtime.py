from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import stat
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware

from agent_shell.automation.context import (
    AutomationContext,
    AutomationRequest,
    AutomationVariables,
    immutable_request,
)
from agent_shell.automation.loader import AutomationPluginLoader
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.validation.service import StaticAssembly


_LOGGER = logging.getLogger("agent_shell.automation")


@dataclass(frozen=True, slots=True)
class AutomationOwner:
    id: str
    type: str
    name: str
    automation: dict[str, Any]
    mapped_paths: Mapping[str, Path]


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


class AutomationRuntime:
    """Request-local plugin state and Shell-owned lifecycle boundaries."""

    def __init__(
        self,
        *,
        request_id: str,
        owners: list[AutomationOwner],
        client_messages: list[dict[str, str]],
        plugins_dir: Path,
        skills_dir: Path,
        runtime_root: Path,
    ) -> None:
        self.request_id = request_id or str(uuid4())
        self._request: AutomationRequest = immutable_request(
            self.request_id,
            client_messages,
        )
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
        self._plugin_variables: dict[tuple[str, int], dict[str, Any]] = {}
        self._skills_dir = skills_dir
        self._request_runtime_dir = (
            runtime_root / "automation" / self.request_id
        ).resolve()
        self._loader = AutomationPluginLoader(
            request_id=self.request_id,
            plugins_dir=plugins_dir,
            runtime_root=runtime_root,
        )
        self._middleware: dict[str, tuple[AgentMiddleware, ...]] = {}
        self._overlay_owners: set[str] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
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
        plugins_dir: Path,
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
                automation=assembly.automation,
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
                    automation=node.automation,
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
            plugins_dir=plugins_dir,
            skills_dir=skills_dir,
            runtime_root=runtime_root,
        )

    @property
    def request(self) -> AutomationRequest:
        return self._request

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

    def input_for(self, owner_id: str, delegated_messages: list[Any]) -> list[Any]:
        return [*self.messages_for(owner_id), *delegated_messages]

    def initial_files_for(self, owner_id: str) -> dict[str, str | bytes]:
        return dict(self._initial_files[owner_id])

    def _variables(self, owner_id: str, binding_index: int) -> AutomationVariables:
        return AutomationVariables(
            self._request_variables,
            self._agent_variables[owner_id],
            self._plugin_variables.setdefault((owner_id, binding_index), {}),
        )

    def _context(
        self,
        owner: AutomationOwner,
        binding_index: int,
        binding: dict[str, Any],
        plugin_dir: Path,
        *,
        stage: str,
        messages: list[dict[str, str]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        tick: int | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> AutomationContext:
        return AutomationContext(
            runtime=self,
            request=self._request,
            owner_id=owner.id,
            owner_type=owner.type,
            owner_name=owner.name,
            binding_index=binding_index,
            plugin_id=str(binding["plugin_id"]),
            plugin_dir=plugin_dir,
            runtime_dir=self.owner_runtime_dir(owner.id),
            mapped_paths=owner.mapped_paths,
            config=dict(binding.get("config", {})),
            variables=self._variables(owner.id, binding_index),
            stage=stage,
            messages=messages,
            initial_files=initial_files,
            tick=tick,
            terminal=terminal,
        )

    async def _run_shell_entrypoint(
        self,
        owner: AutomationOwner,
        binding_index: int,
        binding: dict[str, Any],
        entrypoint: str,
        *,
        messages: list[dict[str, str]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        tick: int | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        plugin_id = str(binding["plugin_id"])
        function, plugin_dir = self._loader.entrypoint(
            owner.id,
            binding_index,
            plugin_id,
            entrypoint,
        )
        if function is None:
            return
        context = self._context(
            owner,
            binding_index,
            binding,
            plugin_dir,
            stage=entrypoint,
            messages=messages,
            initial_files=initial_files,
            tick=tick,
            terminal=terminal,
        )
        try:
            await function(context)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise AgentRuntimeError(
                "automation_plugin_failed",
                f"Automation plugin {plugin_id!r} failed during {entrypoint} for Agent {owner.name!r}.",
                status_code=422,
            ) from exc

    async def prepare(self) -> None:
        from agent_shell.runtime.agent_builder import validate_openai_messages

        for owner in self._owners:
            for binding_index, binding in enumerate(owner.automation.get("plugins", [])):
                if not binding.get("enabled", True):
                    continue
                await self._run_shell_entrypoint(
                    owner,
                    binding_index,
                    binding,
                    "prepare",
                    messages=self._messages[owner.id],
                    initial_files=self._initial_files[owner.id],
                )
            self._messages[owner.id] = validate_openai_messages(
                self._messages[owner.id]
            )

    def middleware_for(self, owner_id: str) -> tuple[AgentMiddleware, ...]:
        cached = self._middleware.get(owner_id)
        if cached is not None:
            return cached
        owner = self._owner_by_id[owner_id]
        middleware: list[AgentMiddleware] = []
        for binding_index, binding in enumerate(owner.automation.get("plugins", [])):
            if not binding.get("enabled", True):
                continue
            plugin_id = str(binding["plugin_id"])
            factory, plugin_dir = self._loader.entrypoint(
                owner.id,
                binding_index,
                plugin_id,
                "middleware",
            )
            if factory is None:
                continue
            context = self._context(
                owner,
                binding_index,
                binding,
                plugin_dir,
                stage="middleware",
            )
            try:
                produced = factory(context)
            except Exception as exc:
                raise AgentRuntimeError(
                    "automation_middleware_materialization_failed",
                    f"Automation plugin {plugin_id!r} could not create Middleware.",
                    status_code=422,
                ) from exc
            values: Sequence[Any]
            if isinstance(produced, AgentMiddleware):
                values = (produced,)
            elif isinstance(produced, (list, tuple)):
                values = produced
            else:
                values = ()
            if not values or any(not isinstance(item, AgentMiddleware) for item in values):
                raise AgentRuntimeError(
                    "automation_middleware_invalid",
                    f"Automation plugin {plugin_id!r} must return AgentMiddleware instances.",
                    status_code=422,
                )
            middleware.extend(values)
        result = tuple(middleware)
        self._middleware[owner_id] = result
        return result

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self._stop_event.is_set():
            return
        for owner in self._owners:
            interval = owner.automation.get("lifecycle_interval_seconds")
            if interval is not None:
                self._tasks.append(
                    asyncio.create_task(
                        self._lifecycle_loop(owner, float(interval)),
                        name=f"automation:{self.request_id}:{owner.id}",
                    )
                )
        if self._tasks:
            await asyncio.sleep(0)

    async def _lifecycle_loop(self, owner: AutomationOwner, interval: float) -> None:
        tick = 0
        while not self._stop_event.is_set():
            try:
                for binding_index, binding in enumerate(owner.automation.get("plugins", [])):
                    if binding.get("enabled", True):
                        await self._run_shell_entrypoint(
                            owner,
                            binding_index,
                            binding,
                            "lifecycle",
                            tick=tick,
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception(
                    "lifecycle automation stopped request=%s agent=%s",
                    self.request_id,
                    owner.id,
                )
                return
            tick += 1
            if self._stop_event.is_set():
                return
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def finish(self, terminal: Mapping[str, Any]) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for owner in self._owners:
            for binding_index, binding in enumerate(owner.automation.get("plugins", [])):
                if not binding.get("enabled", True):
                    continue
                try:
                    await self._run_shell_entrypoint(
                        owner,
                        binding_index,
                        binding,
                        "complete",
                        terminal=terminal,
                    )
                except Exception:
                    _LOGGER.exception(
                        "complete automation failed request=%s agent=%s plugin=%s",
                        self.request_id,
                        owner.id,
                        binding.get("plugin_id", ""),
                    )
        self._loader.close()
        if self._request_runtime_dir.exists():
            shutil.rmtree(self._request_runtime_dir, ignore_errors=True)
