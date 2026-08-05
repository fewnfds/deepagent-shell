from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
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
    immutable_request,
)
from agent_shell.automation.loader import AutomationPluginLoader
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.validation.service import StaticAssembly


_LOGGER = logging.getLogger("agent_shell.automation")

_MIDDLEWARE_HOOKS = (
    "before_agent",
    "abefore_agent",
    "before_model",
    "abefore_model",
    "wrap_model_call",
    "awrap_model_call",
    "after_model",
    "aafter_model",
    "wrap_tool_call",
    "awrap_tool_call",
    "after_agent",
    "aafter_agent",
)
_ASYNC_MIDDLEWARE_HOOKS = frozenset({
    "abefore_agent",
    "abefore_model",
    "awrap_model_call",
    "aafter_model",
    "awrap_tool_call",
    "aafter_agent",
})


class _AutomationMiddlewareBinding(AgentMiddleware):
    """Give one plugin-produced Middleware a graph-unique binding identity."""

    def __init__(self, middleware: AgentMiddleware, name: str) -> None:
        self._middleware = middleware
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def state_schema(self) -> Any:
        return self._middleware.state_schema

    @property
    def tools(self) -> Any:
        return getattr(self._middleware, "tools", ())

    @property
    def transformers(self) -> Any:
        return getattr(self._middleware, "transformers", ())

    def __getattr__(self, name: str) -> Any:
        return getattr(self._middleware, name)


def _sync_middleware_delegate(hook: str) -> Any:
    def delegated(
        self: _AutomationMiddlewareBinding,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return getattr(self._middleware, hook)(*args, **kwargs)

    delegated.__name__ = hook
    return delegated


def _async_middleware_delegate(hook: str) -> Any:
    async def delegated(
        self: _AutomationMiddlewareBinding,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await getattr(self._middleware, hook)(*args, **kwargs)

    delegated.__name__ = hook
    return delegated


def _bind_automation_middleware(
    middleware: AgentMiddleware,
    *,
    name: str,
) -> AgentMiddleware:
    namespace: dict[str, Any] = {}
    middleware_type = type(middleware)
    for hook in _MIDDLEWARE_HOOKS:
        if getattr(middleware_type, hook) is getattr(AgentMiddleware, hook):
            continue
        namespace[hook] = (
            _async_middleware_delegate(hook)
            if hook in _ASYNC_MIDDLEWARE_HOOKS
            else _sync_middleware_delegate(hook)
        )
    binding_type = type(
        f"Bound{middleware_type.__name__}",
        (_AutomationMiddlewareBinding,),
        namespace,
    )
    return binding_type(middleware, name)


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
        client_messages: list[dict[str, Any]],
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
        self._messages: dict[str, list[dict[str, Any]]] = {
            owner.id: [] for owner in owners
        }
        self._initial_files: dict[str, dict[str, str | bytes]] = {
            owner.id: {} for owner in owners
        }
        self._variables: dict[Any, Any] = {}
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
        client_messages: list[dict[str, Any]],
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
        path = self._request_runtime_dir / "owners" / owner_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def binding_runtime_dir(
        self,
        owner_id: str,
        binding_kind: str,
        binding_index: int,
    ) -> Path:
        path = (
            self.owner_runtime_dir(owner_id)
            / "bindings"
            / f"{binding_kind}-{binding_index}"
        )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _invocation(
        self,
        owner_id: str,
        *,
        parent: Mapping[str, Any] | None,
        cause_tool_call_id: str,
    ) -> Mapping[str, Any]:
        owner = self._owner_by_id[owner_id]
        invocation_id = str(uuid4())
        workspaces: dict[str, Path] = {}
        for binding_index, binding in enumerate(owner.automation.get("hooks", [])):
            if not binding.get("enabled", True):
                continue
            scratch = (
                self.binding_runtime_dir(owner_id, "hook", binding_index)
                / "invocations"
                / invocation_id
                / "scratch"
            )
            scratch.mkdir(parents=True, exist_ok=False)
            workspaces[f"hook:{binding_index}"] = scratch
        return MappingProxyType(
            {
                "request_id": self.request_id,
                "id": invocation_id,
                "parent_id": str(parent["id"]) if parent is not None else "",
                "cause_tool_call_id": cause_tool_call_id,
                "agent_id": owner.id,
                "agent_type": owner.type,
                "agent_name": owner.name,
                "workspaces": MappingProxyType(workspaces),
            }
        )

    def root_context(self, owner_id: str) -> dict[str, Any]:
        return {
            "automation_runtime": self,
            "agent_shell_invocation": self._invocation(
                owner_id,
                parent=None,
                cause_tool_call_id="",
            ),
        }

    def child_context(
        self,
        owner_id: str,
        parent: Mapping[str, Any],
        cause_tool_call_id: str,
    ) -> dict[str, Any]:
        return {
            "automation_runtime": self,
            "agent_shell_invocation": self._invocation(
                owner_id,
                parent=parent,
                cause_tool_call_id=cause_tool_call_id,
            ),
        }

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

    def messages_for(self, owner_id: str) -> list[dict[str, Any]]:
        return deepcopy(self._messages[owner_id])

    def has_messages_for(self, owner_id: str) -> bool:
        return bool(self._messages[owner_id])

    def input_for(self, owner_id: str, delegated_messages: list[Any]) -> list[Any]:
        return [*self.messages_for(owner_id), *delegated_messages]

    def initial_files_for(self, owner_id: str) -> dict[str, str | bytes]:
        return dict(self._initial_files[owner_id])

    def _context(
        self,
        owner: AutomationOwner,
        binding_kind: str,
        binding_index: int,
        binding: dict[str, Any],
        plugin_dir: Path,
        *,
        stage: str,
        messages: list[dict[str, Any]] | None = None,
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
            binding_kind=binding_kind,
            binding_index=binding_index,
            plugin_id=str(binding["plugin_id"]),
            plugin_dir=plugin_dir,
            runtime_dir=self.binding_runtime_dir(
                owner.id, binding_kind, binding_index
            ),
            mapped_paths=owner.mapped_paths,
            config=dict(binding.get("config", {})),
            variables=self._variables,
            stage=stage,
            messages=messages,
            initial_files=initial_files,
            tick=tick,
            terminal=terminal,
        )

    async def _run_shell_entrypoint(
        self,
        owner: AutomationOwner,
        binding_kind: str,
        binding_index: int,
        binding: dict[str, Any],
        entrypoint: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        initial_files: dict[str, str | bytes] | None = None,
        tick: int | None = None,
        terminal: Mapping[str, Any] | None = None,
    ) -> None:
        plugin_id = str(binding["plugin_id"])
        function, plugin_dir = self._loader.entrypoint(
            owner.id,
            binding_kind,
            binding_index,
            plugin_id,
            entrypoint,
        )
        if function is None:
            return
        context = self._context(
            owner,
            binding_kind,
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
        from agent_shell.runtime.input_messages import validate_prepared_messages

        for owner in self._owners:
            for binding_index, binding in enumerate(owner.automation.get("hooks", [])):
                if not binding.get("enabled", True):
                    continue
                await self._run_shell_entrypoint(
                    owner,
                    "hook",
                    binding_index,
                    binding,
                    "prepare",
                    messages=self._messages[owner.id],
                    initial_files=self._initial_files[owner.id],
                )
            self._messages[owner.id] = validate_prepared_messages(
                self._messages[owner.id]
            )

    def middleware_for(self, owner_id: str) -> tuple[AgentMiddleware, ...]:
        cached = self._middleware.get(owner_id)
        if cached is not None:
            return cached
        owner = self._owner_by_id[owner_id]
        middleware: list[AgentMiddleware] = []
        middleware_names: set[str] = set()
        for binding_index, binding in enumerate(owner.automation.get("hooks", [])):
            if not binding.get("enabled", True):
                continue
            plugin_id = str(binding["plugin_id"])
            factory, plugin_dir = self._loader.entrypoint(
                owner.id,
                "hook",
                binding_index,
                plugin_id,
                "middleware",
            )
            if factory is None:
                continue
            context = self._context(
                owner,
                "hook",
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
            for produced_index, item in enumerate(values):
                original_name = item.name
                if original_name not in middleware_names:
                    middleware.append(item)
                    middleware_names.add(original_name)
                    continue
                binding_name = (
                    f"{original_name}:automation:{owner.id}:hook:"
                    f"{binding_index}:{produced_index}:{plugin_id}"
                )
                bound = _bind_automation_middleware(item, name=binding_name)
                middleware.append(bound)
                middleware_names.add(bound.name)
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
            for binding_index, binding in enumerate(
                owner.automation.get("periodic", [])
            ):
                if not binding.get("enabled", True):
                    continue
                self._tasks.append(
                    asyncio.create_task(
                        self._lifecycle_loop(owner, binding_index, binding),
                        name=(
                            f"automation:{self.request_id}:{owner.id}:"
                            f"periodic:{binding_index}"
                        ),
                    )
                )
        if self._tasks:
            await asyncio.sleep(0)

    async def _lifecycle_loop(
        self,
        owner: AutomationOwner,
        binding_index: int,
        binding: dict[str, Any],
    ) -> None:
        tick = 0
        interval = float(binding["interval_seconds"])
        while not self._stop_event.is_set():
            try:
                await self._run_shell_entrypoint(
                    owner,
                    "periodic",
                    binding_index,
                    binding,
                    "lifecycle",
                    tick=tick,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception(
                    "periodic automation stopped request=%s agent=%s plugin=%s",
                    self.request_id,
                    owner.id,
                    binding.get("plugin_id", ""),
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
            for binding_kind, bindings in (
                ("hook", owner.automation.get("hooks", [])),
                ("periodic", owner.automation.get("periodic", [])),
            ):
                for binding_index, binding in enumerate(bindings):
                    if not binding.get("enabled", True):
                        continue
                    try:
                        await self._run_shell_entrypoint(
                            owner,
                            binding_kind,
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
