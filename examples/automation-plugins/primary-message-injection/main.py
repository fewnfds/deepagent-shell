from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from agent_shell.automation.messages import (
    mutable_request_messages,
    prepared_transformed_messages,
)


Transform = Callable[[list[dict[str, Any]], Any, Any, Any], Awaitable[object]]


def _compile_transform(source: object) -> Transform | None:
    if not isinstance(source, str) or not source.strip():
        return None
    namespace: dict[str, Any] = {}
    exec(compile(source, "<primary-message-transform>", "exec"), namespace)
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


async def prepare(ctx: Any) -> None:
    if ctx.agent["type"] != "primary":
        return
    try:
        messages = mutable_request_messages(ctx.request.messages)
        transform = _compile_transform(ctx.config.get("transform_source"))
        transformed = (
            await transform(messages, ctx, None, None)
            if transform is not None
            else messages
        )
        ctx.messages.extend(prepared_transformed_messages(transformed))
    except Exception:
        raise RuntimeError("Primary message transform failed") from None
