from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from deepagents.backends.utils import file_data_to_string
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages.utils import convert_to_messages, convert_to_openai_messages
from langgraph.runtime import Runtime
from langgraph.types import Overwrite

from agent_shell.middleware_packages.messages import mutable_request_messages
from agent_shell.runtime.workflow_lifecycle import (
    LIFECYCLE_INPUT_KEY,
    lifecycle_input_namespace,
    lifecycle_invocations_namespace,
)


# 这份配置只属于从示例创建出来的当前 Middleware 实例。
# attachments 为空时不会读取文件；取消下面示例项的注释即可附加 Workflow 文件。
WIC_CONFIG: dict[str, Any] = {
    "attachments": [
        # {
        #     "role": "user",
        #     "path": "/task.md",
        #     "fallback_paths": ["/task-fallback.md"],
        #     "literal": "文件都不存在时使用的文本",
        #     "max_chars": 200_000,
        #     "stop_if_missing": False,
        # },
    ],
    # 只保留开头连续的 system 消息；后续 system 消息改为 user。
    "convert_non_leading_system_to_user": False,
}


async def load_invocation_artifact(
    runtime: Runtime[Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    context = runtime.context
    result_ref = str(record.get("result_ref", ""))
    if runtime.store is None or not result_ref:
        raise RuntimeError("workflow invocation artifact is unavailable")
    item = await runtime.store.aget(
        lifecycle_invocations_namespace(context.lifecycle_id, context.run_id),
        result_ref,
    )
    value = getattr(item, "value", None)
    if not isinstance(value, dict):
        raise RuntimeError("workflow invocation artifact is unavailable")
    return deepcopy(value)


async def customize_context_messages(
    state: dict[str, Any],
    runtime: Runtime[Any],
    request_messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从 Lifecycle Store 输入创建并改造当前 Agent 的消息。"""

    user_messages = mutable_request_messages(request_messages)

    # ---- 在这里编写当前 WIC 变种自己的消息选择、裁剪和重排逻辑。 ----
    # 可读取：state、context、state["workflow_state_snapshot"]。
    # 例如先从快照的 agent_invocations 选择轻量引用，再调用
    # await load_invocation_artifact(runtime, record) 读取完整 messages。

    return user_messages


async def _initial_messages(
    state: dict[str, Any],
    runtime: Runtime[Any],
    *,
    scope: str,
) -> list[dict[str, Any]]:
    if scope == "subagent":
        # Subagent 的输入是 Main Agent 委派给它的私有 messages。
        return deepcopy(convert_to_openai_messages(convert_to_messages(state.get("messages", []))))
    # Workflow Agent 的原始输入位于 Lifecycle Store；不进入 root State 或 Context。
    context = getattr(runtime, "context", None)
    store = getattr(runtime, "store", None)
    lifecycle_id = str(getattr(context, "lifecycle_id", ""))
    if store is None or not lifecycle_id:
        raise RuntimeError("workflow lifecycle input is unavailable")
    item = await store.aget(
        lifecycle_input_namespace(lifecycle_id),
        LIFECYCLE_INPUT_KEY,
    )
    value = getattr(item, "value", None)
    request_messages = value.get("messages") if isinstance(value, dict) else None
    if not isinstance(request_messages, list):
        raise RuntimeError("workflow lifecycle input is unavailable")
    return await customize_context_messages(state, runtime, request_messages)


def _validate_virtual_path(path: str) -> str:
    if not path.startswith("/") or "\\" in path or "\x00" in path:
        raise ValueError("attachment path must be an absolute virtual path")
    if any(part in {"", ".", ".."} for part in path.split("/")[1:]):
        raise ValueError("attachment path must be normalized")
    return path


async def build_workflow_input_context(
    messages: list[dict[str, Any]],
    *,
    read_file: Callable[[str], Awaitable[str | None]],
) -> list[dict[str, Any]]:
    """集中完成当前 WIC 的变化逻辑；不需要的区块可直接从本函数删除。"""

    result = deepcopy(messages)

    # ---- 可选功能 1：把 Workflow 虚拟文件附加到上下文。 ----
    for attachment in WIC_CONFIG["attachments"]:
        content: str | None = None
        candidates = [attachment.get("path"), *attachment.get("fallback_paths", [])]
        for path in candidates:
            if path:
                content = await read_file(path)
                if content is not None:
                    break
        if content is None:
            content = attachment.get("literal") or None
        if content is None:
            if attachment.get("stop_if_missing", False):
                break
            continue
        max_chars = attachment.get("max_chars")
        if isinstance(max_chars, int) and max_chars > 0:
            content = content[:max_chars]
        result.append(
            {
                "role": attachment.get("role", "user"),
                "content": content,
            }
        )

    # ---- 可选功能 2：把不在开头连续区域内的 system 消息改成 user。 ----
    if WIC_CONFIG["convert_non_leading_system_to_user"]:
        leading_system = True
        for message in result:
            if leading_system and message.get("role") == "system":
                continue
            leading_system = False
            if message.get("role") == "system":
                message["role"] = "user"

    return result


class WorkflowInputContextMiddleware(AgentMiddleware):
    def __init__(self, *, backend: Any, scope: str, package_id: str) -> None:
        super().__init__()
        self._middleware_name = f"WorkflowInputContextMiddleware_{package_id}"
        self._backend = backend
        self._scope = scope

    @property
    def name(self) -> str:
        # 每个配置使用自己的 package ID，允许同一 Agent 装配多个 WIC 变种。
        return self._middleware_name

    async def _read_file(self, path: str) -> str | None:
        normalized = _validate_virtual_path(path)
        if self._backend is None:
            return None
        result = await self._backend.aread(normalized, offset=0, limit=1_000_000)
        if getattr(result, "file_data", None) is None:
            if "not found" in str(getattr(result, "error", "")).lower():
                return None
            raise RuntimeError("workflow attachment could not be read")
        return file_data_to_string(result.file_data)

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any]:
        messages = await _initial_messages(state, runtime, scope=self._scope)
        messages = await build_workflow_input_context(
            messages,
            read_file=self._read_file,
        )
        return {"messages": Overwrite(convert_to_messages(messages))}


def create_middleware(
    backend: Any,
    scope: str,
    package_id: str,
    **_available: Any,
) -> AgentMiddleware:
    return WorkflowInputContextMiddleware(
        backend=backend,
        scope=scope,
        package_id=package_id,
    )
