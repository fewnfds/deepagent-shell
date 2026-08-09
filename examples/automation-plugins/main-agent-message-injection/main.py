from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from agent_shell.automation.messages import (
    mutable_request_messages,
    prepared_transformed_messages,
)


Transform = Callable[[list[dict[str, Any]], Any, Any, Any], Awaitable[object]]


def _compile_transform(source: object) -> Transform | None:
    if not isinstance(source, str) or not source.strip():
        return None
    namespace: dict[str, Any] = {}
    exec(compile(source, "<main-agent-message-transform>", "exec"), namespace)
    transform = namespace.get("transform_messages")
    if not inspect.iscoroutinefunction(transform):
        raise ValueError("transform_messages must be an async function")
    signature = inspect.signature(transform)
    parameters = tuple(signature.parameters.values())
    if (
        tuple(parameter.name for parameter in parameters)
        != ("messages", "ctx", "state", "runtime")
        or any(
            parameter.kind
            not in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
            for parameter in parameters
        )
    ):
        raise ValueError(
            "transform_messages must accept messages, ctx, state, runtime"
        )
    return transform


class MainAgentMessageInjectionMiddleware(AgentMiddleware):
    def __init__(self, ctx: Any) -> None:
        super().__init__()
        self._ctx = ctx
        try:
            self._transform = _compile_transform(ctx.config.get("transform_source"))
        except Exception:
            raise RuntimeError("Main Agent message transform is invalid") from None

    async def abefore_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        if self._ctx.agent["type"] != "main_agent":
            return None
        try:
            messages = mutable_request_messages(self._ctx.request.messages)
            transformed = (
                await self._transform(messages, self._ctx, state, runtime)
                if self._transform is not None
                else messages
            )
            prepared = prepared_transformed_messages(transformed)
        except Exception:
            raise RuntimeError("Main Agent message transform failed") from None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *prepared,
            ]
        }


def create_middleware(ctx: Any) -> AgentMiddleware:
    return MainAgentMessageInjectionMiddleware(ctx)
