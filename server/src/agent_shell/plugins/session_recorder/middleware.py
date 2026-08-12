from __future__ import annotations

import builtins
from copy import deepcopy
from typing import Any, Callable
from uuid import uuid4

from deepagents.backends.utils import file_data_to_string
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import convert_to_messages, convert_to_openai_messages
from langgraph.runtime import Runtime

from agent_shell.plugins.workflow_input_context.contracts import validate_virtual_path

from .contracts import SessionRecorderBlock


class SessionRecorderError(RuntimeError):
    """Safe runtime error raised without script or provider details."""


def _compile_transform(source: str) -> Callable[..., Any]:
    namespace: dict[str, Any] = {"__builtins__": builtins.__dict__}
    try:
        exec(compile(source, "<session-recorder-transform>", "exec"), namespace, namespace)
    except Exception as exc:
        raise SessionRecorderError("session transform could not be loaded") from exc
    transform = namespace.get("transform")
    if not callable(transform):
        raise SessionRecorderError("session transform is not callable")
    return transform


def _copy_conversation_messages(value: object) -> list[dict[str, Any]]:
    try:
        return deepcopy(
            convert_to_openai_messages(
                convert_to_messages(value),
                include_id=False,
            )
        )
    except Exception as exc:
        raise SessionRecorderError("session messages are invalid") from exc


class SessionRecorderMiddleware(AgentMiddleware):
    name = "SessionRecorderMiddleware"

    def __init__(
        self,
        block: SessionRecorderBlock,
        *,
        backend: Any,
        agent_scope: str,
        agent_id: str,
        agent_name: str,
        workflow_node_id: str | None,
    ) -> None:
        super().__init__()
        self._block = block
        self._backend = backend
        self._agent_scope = agent_scope
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._workflow_node_id = workflow_node_id
        self._transform = (
            _compile_transform(block.custom_transform_source)
            if block.custom_transform_enabled
            else None
        )

    def _read_file(self, path: str) -> str | None:
        try:
            normalized_path = validate_virtual_path(path)
        except (TypeError, ValueError) as exc:
            raise SessionRecorderError("session filesystem path is invalid") from exc
        if self._backend is None:
            return None
        try:
            result = self._backend.read(normalized_path, offset=0, limit=1_000_000)
        except Exception as exc:
            raise SessionRecorderError("session filesystem read failed") from exc
        if getattr(result, "file_data", None) is None:
            if "not found" in str(getattr(result, "error", "")).lower():
                return None
            raise SessionRecorderError("session filesystem read failed")
        try:
            return file_data_to_string(result.file_data)
        except Exception as exc:
            raise SessionRecorderError("session filesystem content is invalid") from exc

    def _run(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any]:
        try:
            messages = _copy_conversation_messages(state.get("messages", ()))
            if self._transform is not None:
                messages = _copy_conversation_messages(
                    self._transform(
                        messages=deepcopy(messages),
                        read_file=self._read_file,
                        config=deepcopy(self._block.model_dump(mode="json")),
                        state=state,
                        context=getattr(runtime, "context", None),
                    )
                )
        except SessionRecorderError:
            raise
        except Exception as exc:
            raise SessionRecorderError("session transform failed") from exc
        session_id = str(uuid4())
        return {
            "agent_sessions": {
                session_id: {
                    "session_id": session_id,
                    "agent_scope": self._agent_scope,
                    "agent_id": self._agent_id,
                    "agent_name": self._agent_name,
                    "workflow_node_id": self._workflow_node_id,
                    "messages": messages,
                }
            }
        }

    def after_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any]:
        return self._run(state, runtime)

    async def aafter_agent(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any]:
        return self._run(state, runtime)


__all__ = ["SessionRecorderError", "SessionRecorderMiddleware"]
