from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware

from agent_shell.middleware_packages.context import (
    MiddlewarePackageContext,
    MiddlewareRequest,
    LifecycleSnapshot,
    freeze,
    immutable_request,
)
from agent_shell.middleware_packages.loader import MiddlewarePackageLoader
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.input_messages import client_messages_sha
from agent_shell.validation.service import StaticAssembly


@dataclass(frozen=True, slots=True)
class MiddlewareOwner:
    id: str
    type: str
    name: str
    bindings: tuple[dict[str, Any], ...]
    mapped_paths: Mapping[str, Path]


def _assembly_snapshot(
    assembly: StaticAssembly,
    *,
    main_agent_id: str,
) -> dict[str, Any]:
    nodes = []
    for key in sorted(assembly.subagent_nodes):
        node = assembly.subagent_nodes[key]
        nodes.append(
            {
                "id": node.key,
                "component_name": node.component_name,
                "name": node.name,
                "description": node.description,
                "references": deepcopy(node.references),
                "blocks": deepcopy(node.blocks),
                "filesystem_mode": node.filesystem_mode,
            }
        )
    return {
        "main_agent": {
            "id": main_agent_id,
            "component_name": str(assembly.main_agent.get("component_name", "")),
            "name": str(assembly.main_agent.get("name", "")),
            "references": deepcopy(assembly.references),
            "blocks": deepcopy(assembly.blocks),
            "filesystem_mode": assembly.filesystem_mode,
            "subagents": [edge.target_key for edge in assembly.subagents],
        },
        "subagent_nodes": nodes,
    }


def _stable_sha(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _agent_shas(snapshot: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    main_agent = snapshot.get("main_agent")
    if isinstance(main_agent, Mapping):
        values[str(main_agent.get("id", ""))] = _stable_sha(main_agent)
    for node in snapshot.get("subagent_nodes", []):
        if isinstance(node, Mapping):
            values[str(node.get("id", ""))] = _stable_sha(node)
    return values


class MiddlewarePackageRuntime:
    """Request-local Middleware materialization and immutable input snapshot."""

    def __init__(
        self,
        *,
        request_id: str,
        owners: list[MiddlewareOwner],
        client_messages: list[dict[str, Any]],
        assembly_snapshot: dict[str, Any] | None = None,
        packages_dir: Path,
        runtime_root: Path,
    ) -> None:
        self.request_id = request_id or str(uuid4())
        self._request: MiddlewareRequest = immutable_request(
            self.request_id,
            client_messages,
        )
        snapshot = deepcopy(assembly_snapshot or {})
        self._lifecycle = LifecycleSnapshot(
            request_id=self.request_id,
            messages=self._request.messages,
            assembly=freeze(snapshot),
            input_sha=client_messages_sha(client_messages),
            agent_shas=MappingProxyType(_agent_shas(snapshot)),
            assembly_sha=_stable_sha(snapshot),
        )
        self._owners = owners
        self._owner_by_id = {owner.id: owner for owner in owners}
        self._request_runtime_dir = (
            runtime_root / "middleware_packages" / self.request_id
        ).resolve()
        self._loader = MiddlewarePackageLoader(
            request_id=self.request_id,
            packages_dir=packages_dir,
            runtime_root=runtime_root,
        )
        self._middleware: dict[str, tuple[AgentMiddleware, ...]] = {}
        self._closed = False

    @classmethod
    def from_assembly(
        cls,
        assembly: StaticAssembly,
        client_messages: list[dict[str, Any]],
        *,
        main_agent_id: str,
        request_id: str,
        packages_dir: Path,
        runtime_root: Path,
    ) -> "MiddlewarePackageRuntime":
        owners: list[MiddlewareOwner] = []

        def middleware_bindings(
            blocks: dict[str, dict[str, Any]],
        ) -> tuple[dict[str, Any], ...]:
            selected = blocks.get("custom-middleware", {})
            return tuple(deepcopy(selected.get("middlewares", [])))

        def mapped_paths(blocks: dict[str, dict[str, Any]]) -> Mapping[str, Path]:
            filesystem = blocks.get("filesystem", {})
            values = {
                str(item["virtual_path"]): Path(str(item["local_path"])).resolve()
                for item in filesystem.get("mapped_directories", [])
            }
            return MappingProxyType(values)

        owners.append(
            MiddlewareOwner(
                id=main_agent_id,
                type="main_agent",
                name=str(assembly.main_agent.get("name", "")),
                bindings=middleware_bindings(assembly.blocks),
                mapped_paths=mapped_paths(assembly.blocks),
            )
        )
        for edge in assembly.subagents:
            key = str(edge.target_key)
            node = assembly.subagent_nodes[key]
            owners.append(
                MiddlewareOwner(
                    id=node.key,
                    type="subagent",
                    name=node.name,
                    bindings=middleware_bindings(node.blocks),
                    mapped_paths=mapped_paths(node.blocks),
                )
            )
        return cls(
            request_id=request_id,
            owners=owners,
            client_messages=client_messages,
            assembly_snapshot=_assembly_snapshot(
                assembly,
                main_agent_id=main_agent_id,
            ),
            packages_dir=packages_dir,
            runtime_root=runtime_root,
        )

    @property
    def request(self) -> MiddlewareRequest:
        return self._request

    @property
    def lifecycle(self) -> LifecycleSnapshot:
        return self._lifecycle

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

    def _context(
        self,
        owner: MiddlewareOwner,
        binding_kind: str,
        binding_index: int,
        binding: dict[str, Any],
        package_dir: Path,
    ) -> MiddlewarePackageContext:
        return MiddlewarePackageContext(
            request=self._request,
            owner_id=owner.id,
            owner_type=owner.type,
            owner_name=owner.name,
            binding_kind=binding_kind,
            binding_index=binding_index,
            package_id=str(binding["package_id"]),
            package_dir=package_dir,
            runtime_dir=self.binding_runtime_dir(
                owner.id, binding_kind, binding_index
            ),
            mapped_paths=owner.mapped_paths,
            config=dict(binding.get("config", {})),
        )

    def middleware_for(self, owner_id: str) -> tuple[AgentMiddleware, ...]:
        cached = self._middleware.get(owner_id)
        if cached is not None:
            return cached
        owner = self._owner_by_id[owner_id]
        middleware: list[AgentMiddleware] = []
        for binding_index, binding in enumerate(
            owner.bindings
        ):
            if not binding.get("enabled", True):
                continue
            package_id = str(binding["package_id"])
            factory, package_dir = self._loader.entrypoint(
                owner.id,
                "middleware",
                binding_index,
                package_id,
            )
            if factory is None:
                continue
            context = self._context(
                owner,
                "middleware",
                binding_index,
                binding,
                package_dir,
            )
            try:
                produced = factory(context)
            except Exception as exc:
                raise AgentRuntimeError(
                    "middleware_package_materialization_failed",
                    f"Middleware package {package_id!r} could not create Middleware.",
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
                    "middleware_package_result_invalid",
                    f"Middleware package {package_id!r} must return AgentMiddleware instances.",
                    status_code=422,
                )
            middleware.extend(values)
        result = tuple(middleware)
        self._middleware[owner_id] = result
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loader.close()
        if self._request_runtime_dir.exists():
            shutil.rmtree(self._request_runtime_dir, ignore_errors=True)
