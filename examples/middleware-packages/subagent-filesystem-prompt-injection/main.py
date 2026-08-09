from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES


_GROUP_PATTERN = re.compile(r"^\[group:\s*(?P<name>[^\]]+?)\s*\]$")
_ROLE_PATTERN = re.compile(r"^\[(?P<role>assistant|user|system)\]$")
_FILE_PATTERN = re.compile(
    r"^\[(?P<path>/[^\]\r\n]+)\]\[(?P<minimum>[0-9]+)\]$"
)


@dataclass(frozen=True, slots=True)
class FileLayer:
    path: str
    minimum_chars: int


@dataclass(frozen=True, slots=True)
class PromptEntry:
    role: str
    title: str
    layers: tuple[FileLayer, ...]


@dataclass(frozen=True, slots=True)
class PromptGroup:
    name: str
    entries: tuple[PromptEntry, ...]


@dataclass(frozen=True, slots=True)
class FileValue:
    exists: bool
    content: str | None


def _layout_error(line_number: int, detail: str) -> ValueError:
    return ValueError(f"Invalid prompt layout at line {line_number}: {detail}")


def _validate_virtual_file(path: str, line_number: int) -> None:
    parsed = PurePosixPath(path)
    if (
        not path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/")[1:])
        or str(parsed) != path
    ):
        raise _layout_error(line_number, "file paths must be normalized virtual files")


def parse_layout(source: object) -> tuple[PromptGroup, ...]:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Filesystem prompt layout must not be empty")
    lines = source.splitlines()
    groups: list[PromptGroup] = []
    seen_names: set[str] = set()
    index = 0

    def skip_blanks() -> None:
        nonlocal index
        while index < len(lines) and not lines[index].strip():
            index += 1

    while True:
        skip_blanks()
        if index >= len(lines):
            break
        group_match = _GROUP_PATTERN.fullmatch(lines[index])
        if group_match is None:
            raise _layout_error(index + 1, "expected [group: name]")
        name = group_match.group("name").strip()
        if not name or name in seen_names:
            raise _layout_error(index + 1, "group names must be non-empty and unique")
        seen_names.add(name)
        index += 1
        entries: list[PromptEntry] = []

        while True:
            skip_blanks()
            if index >= len(lines) or _GROUP_PATTERN.fullmatch(lines[index]):
                break
            role_match = _ROLE_PATTERN.fullmatch(lines[index])
            if role_match is None:
                raise _layout_error(
                    index + 1,
                    "expected [assistant], [user], or [system]",
                )
            role = role_match.group("role")
            index += 1
            if index >= len(lines) or not lines[index].strip():
                raise _layout_error(
                    index + 1,
                    "expected one non-empty Markdown title line",
                )
            title = lines[index]
            index += 1
            layers: list[FileLayer] = []
            while index < len(lines):
                file_match = _FILE_PATTERN.fullmatch(lines[index])
                if file_match is None:
                    break
                path = file_match.group("path")
                _validate_virtual_file(path, index + 1)
                layers.append(
                    FileLayer(
                        path=path,
                        minimum_chars=int(file_match.group("minimum")),
                    )
                )
                index += 1
            if not layers:
                raise _layout_error(index + 1, "expected at least one [path][minimum] layer")
            entries.append(PromptEntry(role=role, title=title, layers=tuple(layers)))

        if not entries:
            raise _layout_error(
                index + 1,
                "each group must contain at least one prompt entry",
            )
        layer_counts = {len(entry.layers) for entry in entries}
        if len(layer_counts) != 1:
            raise _layout_error(
                index + 1,
                "all entries in one group must declare the same number of layers",
            )
        groups.append(PromptGroup(name=name, entries=tuple(entries)))

    return tuple(groups)


def _mapped_route(ctx: Any, virtual_path: str) -> tuple[str, Path] | None:
    matches = [
        (str(route), Path(root))
        for route, root in ctx.paths.mapped.items()
        if virtual_path.startswith(str(route))
    ]
    return max(matches, key=lambda item: len(item[0]), default=None)


def _read_mapped_file(route: str, root: Path, virtual_path: str) -> FileValue:
    resolved_root = root.resolve()
    relative = virtual_path[len(route) :]
    try:
        target = (resolved_root / relative).resolve()
        target.relative_to(resolved_root)
    except (OSError, ValueError):
        return FileValue(exists=False, content=None)
    if not target.is_file():
        return FileValue(exists=False, content=None)
    try:
        return FileValue(exists=True, content=target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return FileValue(exists=True, content=None)


def _read_state_file(state: Mapping[str, Any], virtual_path: str) -> FileValue:
    files = state.get("files")
    if not isinstance(files, Mapping) or virtual_path not in files:
        return FileValue(exists=False, content=None)
    value = files[virtual_path]
    if not isinstance(value, Mapping) or value.get("encoding") != "utf-8":
        return FileValue(exists=True, content=None)
    content = value.get("content")
    if isinstance(content, str):
        return FileValue(exists=True, content=content)
    if isinstance(content, list) and all(isinstance(line, str) for line in content):
        return FileValue(exists=True, content="".join(content))
    return FileValue(exists=True, content=None)


def _read_file(ctx: Any, state: Mapping[str, Any], virtual_path: str) -> FileValue:
    route = _mapped_route(ctx, virtual_path)
    if route is not None:
        return _read_mapped_file(*route, virtual_path)
    return _read_state_file(state, virtual_path)


def build_prompt_messages(
    groups: tuple[PromptGroup, ...],
    ctx: Any,
    state: Mapping[str, Any],
) -> list[dict[str, str]]:
    values: dict[str, FileValue] = {}
    for group in groups:
        for entry in group.entries:
            for layer in entry.layers:
                if layer.path not in values:
                    values[layer.path] = _read_file(ctx, state, layer.path)
    if not any(value.exists for value in values.values()):
        return []

    messages: list[dict[str, str]] = []
    for group in groups:
        selected_layer = 0
        layer_count = len(group.entries[0].layers)
        for layer_index in range(1, layer_count):
            layer_is_valid = all(
                (value := values[entry.layers[layer_index].path]).content is not None
                and len(value.content) >= entry.layers[layer_index].minimum_chars
                for entry in group.entries
            )
            if not layer_is_valid:
                break
            selected_layer = layer_index

        for entry in group.entries:
            value = values[entry.layers[selected_layer].path]
            body = value.content if value.content is not None else "缺失"
            role = "user" if entry.role == "system" else entry.role
            messages.append(
                {"role": role, "content": f"{entry.title}\n\n{body}"}
            )
    return messages


class SubagentFilesystemPromptMiddleware(AgentMiddleware):
    def __init__(self, ctx: Any) -> None:
        super().__init__()
        self._ctx = ctx
        try:
            self._groups = parse_layout(ctx.config.get("layout"))
        except Exception as exc:
            detail = f"Subagent filesystem prompt layout is invalid: {exc}"
            ctx.log(detail)
            raise RuntimeError(detail) from None

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        if self._ctx.agent["type"] != "subagent":
            return None
        current = list(state.get("messages", []))
        if not current:
            return None
        try:
            prompts = await asyncio.to_thread(
                build_prompt_messages,
                self._groups,
                self._ctx,
                state,
            )
        except Exception:
            raise RuntimeError("Subagent filesystem prompt injection failed") from None
        if not prompts:
            return None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *current[:-1],
                *prompts,
                current[-1],
            ]
        }


def create_middleware(ctx: Any) -> AgentMiddleware:
    return SubagentFilesystemPromptMiddleware(ctx)
