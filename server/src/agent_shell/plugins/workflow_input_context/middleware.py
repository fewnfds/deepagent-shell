from __future__ import annotations

import builtins
from copy import deepcopy
from typing import Any, Callable

from deepagents.backends.utils import file_data_to_string
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages.utils import convert_to_messages
from langgraph.runtime import Runtime

from agent_shell.middleware_packages.messages import mutable_request_messages

from .contracts import WorkflowInputContextBlock, validate_virtual_path


class WorkflowInputContextError(RuntimeError):
    """Safe runtime error raised by the plugin without provider details."""


def _text_length(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(str(part.get("text", "")))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return 0


def _copy_messages(value: object) -> list[dict[str, Any]]:
    try:
        messages = mutable_request_messages(value)
    except Exception as exc:
        raise WorkflowInputContextError("input context messages are invalid") from exc
    return messages


def _promote_system_messages(
    messages: list[dict[str, Any]],
    *,
    enabled: bool,
    minimum_chars: int,
) -> list[dict[str, Any]]:
    if not enabled:
        return messages
    prefix_size = 0
    while prefix_size < len(messages) and messages[prefix_size].get("role") == "system":
        prefix_size += 1
    prefix = messages[:prefix_size]
    promoted: list[dict[str, Any]] = []
    remainder: list[dict[str, Any]] = []
    for message in messages[prefix_size:]:
        if (
            message.get("role") == "system"
            and _text_length(message.get("content")) >= minimum_chars
        ):
            promoted.append(message)
        else:
            remainder.append(message)
    return [*prefix, *promoted, *remainder]


def _demote_non_top_system(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefix_size = 0
    while prefix_size < len(messages) and messages[prefix_size].get("role") == "system":
        prefix_size += 1
    result = deepcopy(messages)
    for message in result[prefix_size:]:
        if message.get("role") == "system":
            message["role"] = "user"
    return result


def _compile_transform(source: str) -> Callable[..., Any]:
    namespace: dict[str, Any] = {"__builtins__": builtins.__dict__}
    try:
        exec(compile(source, "<workflow-input-context-transform>", "exec"), namespace, namespace)
    except Exception as exc:
        raise WorkflowInputContextError("custom input transform could not be loaded") from exc
    transform = namespace.get("transform")
    if not callable(transform):
        raise WorkflowInputContextError("custom input transform is not callable")
    return transform


class WorkflowInputContextMiddleware(AgentMiddleware):
    name = "WorkflowInputContextMiddleware"

    def __init__(self, block: WorkflowInputContextBlock, *, backend: Any, scope: str) -> None:
        super().__init__()
        self._block = block
        self._backend = backend
        self._scope = scope
        self._transform = (
            _compile_transform(block.custom_transform_source)
            if block.custom_transform_enabled and block.custom_transform_source.strip()
            else None
        )

    def _read_file(self, path: str) -> str | None:
        try:
            normalized_path = validate_virtual_path(path)
        except (TypeError, ValueError) as exc:
            raise WorkflowInputContextError(
                "workflow filesystem path is invalid"
            ) from exc
        if self._backend is None:
            return None
        try:
            result = self._backend.read(normalized_path, offset=0, limit=1_000_000)
        except Exception as exc:
            raise WorkflowInputContextError("workflow filesystem read failed") from exc
        if getattr(result, "file_data", None) is None:
            error = str(getattr(result, "error", ""))
            if "not found" in error.lower():
                return None
            raise WorkflowInputContextError("workflow filesystem read failed")
        try:
            return file_data_to_string(result.file_data)
        except Exception as exc:
            raise WorkflowInputContextError("workflow filesystem content is invalid") from exc

    def _apply_slots(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = list(messages)
        for slot in self._block.slots:
            if not slot.enabled:
                continue
            content: str | None = None
            candidates = ([slot.file] if slot.file is not None else []) + list(slot.fallback_files)
            for path in candidates:
                content = self._read_file(path)
                if content is not None:
                    break
            if content is None and slot.literal:
                content = slot.literal
            if content is None:
                if slot.truncate_if_missing:
                    break
                continue
            if slot.max_chars is not None:
                content = content[: slot.max_chars]
            result.append({"role": slot.role, "content": content})
        return result

    def _run(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        if self._scope not in self._block.apply_to:
            return None
        context = getattr(runtime, "context", None)
        raw_messages = getattr(context, "messages", None)
        messages = _copy_messages(raw_messages or ())
        if self._transform is not None:
            try:
                transformed = self._transform(
                    messages,
                    self._read_file,
                    deepcopy(self._block.model_dump(mode="json")),
                )
            except WorkflowInputContextError:
                raise
            except Exception as exc:
                raise WorkflowInputContextError("custom input transform failed") from exc
            messages = _copy_messages(transformed)
        messages = _promote_system_messages(
            messages,
            enabled=self._block.system_promote_enabled,
            minimum_chars=self._block.system_promote_min_chars,
        )
        if self._block.demote_non_top_system:
            messages = _demote_non_top_system(messages)
        messages = self._apply_slots(messages)
        try:
            return {"messages": convert_to_messages(messages)}
        except Exception as exc:
            raise WorkflowInputContextError("input context messages could not be materialized") from exc

    def before_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        return self._run(state, runtime)

    async def abefore_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        return self._run(state, runtime)


__all__ = ["WorkflowInputContextError", "WorkflowInputContextMiddleware"]
