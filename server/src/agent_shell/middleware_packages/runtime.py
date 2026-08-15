from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain.agents.middleware import AgentMiddleware

from agent_shell.python_packages.loader import PythonPackageLoader
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.validation.assembly import StaticAssembly


@dataclass(frozen=True, slots=True)
class MiddlewareOwner:
    id: str
    type: str
    name: str
    package_owner_id: str
    package: dict[str, Any] | None


class MiddlewarePackageRuntime:
    """Request-local package loading and official Middleware materialization.

    The package boundary deliberately stays smaller than LangChain's runtime:
    package configuration and the owning Agent identity are constructor data.
    During execution, a returned ``AgentMiddleware`` reads graph state and
    ``Runtime.context`` through LangChain's official hooks.
    """

    def __init__(
        self,
        *,
        request_id: str,
        owners: list[MiddlewareOwner],
        packages_dir: Path,
        runtime_root: Path,
    ) -> None:
        self.request_id = request_id or str(uuid4())
        self._owners = owners
        self._owner_by_id = {owner.id: owner for owner in owners}
        self._loader = PythonPackageLoader(
            request_id=self.request_id,
            packages_dir=packages_dir,
            runtime_root=runtime_root,
            family="middleware",
            adapter="agent-middleware",
            factory_name="create_middleware",
            factory_parameters=("agent",),
        )
        self._middleware: dict[str, tuple[AgentMiddleware, ...]] = {}
        self._closed = False

    @classmethod
    def from_assembly(
        cls,
        assembly: StaticAssembly,
        *,
        main_agent_id: str,
        request_id: str,
        packages_dir: Path,
        runtime_root: Path,
    ) -> "MiddlewarePackageRuntime":
        owners: list[MiddlewareOwner] = []

        def middleware_package(
            blocks: dict[str, dict[str, Any]],
        ) -> dict[str, Any] | None:
            selected = blocks.get("custom-middleware", {})
            package = selected.get("python_package")
            return deepcopy(package) if isinstance(package, dict) else None

        owners.append(
            MiddlewareOwner(
                id=main_agent_id,
                type="main_agent",
                name=str(assembly.main_agent.get("name", "")),
                package_owner_id=str(
                    assembly.blocks.get("custom-middleware", {}).get("id", "")
                ),
                package=middleware_package(assembly.blocks),
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
                    package_owner_id=str(
                        node.blocks.get("custom-middleware", {}).get("id", "")
                    ),
                    package=middleware_package(node.blocks),
                )
            )
        return cls(
            request_id=request_id,
            owners=owners,
            packages_dir=packages_dir,
            runtime_root=runtime_root,
        )

    def middleware_for(self, owner_id: str) -> tuple[AgentMiddleware, ...]:
        cached = self._middleware.get(owner_id)
        if cached is not None:
            return cached
        owner = self._owner_by_id[owner_id]
        if owner.package is None:
            result: tuple[AgentMiddleware, ...] = ()
            self._middleware[owner_id] = result
            return result
        folder = str(owner.package["folder"])
        factory, metadata, _package_dir = self._loader.entrypoint(
            owner.id,
            "middleware",
            0,
            folder,
            package_owner_id=owner.package_owner_id,
        )
        try:
            produced = factory(
                {
                    "id": owner.id,
                    "type": owner.type,
                    "name": owner.name,
                    "package_id": metadata["id"],
                },
            )
        except Exception as exc:
            raise AgentRuntimeError(
                "middleware_package_materialization_failed",
                f"Middleware package {folder!r} could not create Middleware.",
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
                f"Middleware package {folder!r} must return AgentMiddleware instances.",
                status_code=422,
            )
        for item in values:
            middleware_type = type(item)
            for sync_name, async_name in (
                ("before_agent", "abefore_agent"),
                ("before_model", "abefore_model"),
                ("after_model", "aafter_model"),
                ("after_agent", "aafter_agent"),
                ("wrap_model_call", "awrap_model_call"),
                ("wrap_tool_call", "awrap_tool_call"),
            ):
                if (
                    getattr(middleware_type, sync_name)
                    is not getattr(AgentMiddleware, sync_name)
                    and getattr(middleware_type, async_name)
                    is getattr(AgentMiddleware, async_name)
                ):
                    raise AgentRuntimeError(
                        "middleware_package_async_hook_required",
                        (
                            f"Middleware package {folder!r} implements "
                            f"{sync_name} without {async_name}."
                        ),
                        status_code=422,
                    )
        result = tuple(values)
        self._middleware[owner_id] = result
        return result

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loader.close()


__all__ = ["MiddlewareOwner", "MiddlewarePackageRuntime"]
