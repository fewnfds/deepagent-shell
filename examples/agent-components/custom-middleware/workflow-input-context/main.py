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


# 这份配置只属于从示例创建出来的当前 Middleware 实例。
# attachments 为空时不会读取文件；取消下面示例项的注释即可附加 Workflow 文件。
WIC_CONFIG: dict[str, Any] = {
    "attachments": [
        # {
        #     "role": "user",
        #     "path": "/task.md",
        #     "fallback_paths": ["/task-fallback.md"],
        #     "literal": "文件都不存在时使用的文本",
        #     "max_chars": 20_000,
        #     "stop_if_missing": False,
        # },
    ],
    # 只保留开头连续的 system 消息；后续 system 消息改为 user。
    "convert_non_leading_system_to_user": False,
}


def _initial_messages(
    state: dict[str, Any],
    runtime: Runtime[Any],
    *,
    scope: str,
) -> list[dict[str, Any]]:
    if scope == "subagent":
        # Subagent 的输入是 Main Agent 委派给它的私有 messages。
        return deepcopy(convert_to_openai_messages(convert_to_messages(state.get("messages", []))))
    # Workflow Agent 的原始输入只在 runtime.context 中；不从 Workflow root State 取整包消息。
    context = getattr(runtime, "context", None)
    return mutable_request_messages(getattr(context, "messages", None) or ())


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
    state: dict[str, Any],
    runtime: Runtime[Any],
) -> list[dict[str, Any]]:
    """集中完成当前 WIC 的变化逻辑；不需要的区块可直接从本函数删除。"""

    result = deepcopy(messages)

    # ---- 在这里编写当前 WIC 变种自己的消息选择、裁剪和重排逻辑。 ----
    # 可读取：state、runtime.context、runtime.context.workflow_state。
    # 例如可以从 workflow_state["agent_invocations"] 选择前序 Agent 的结果，
    # 然后直接替换 result。不要修改 runtime.context.messages 本身。

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
        messages = _initial_messages(state, runtime, scope=self._scope)
        messages = await build_workflow_input_context(
            messages,
            read_file=self._read_file,
            state=state,
            runtime=runtime,
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
