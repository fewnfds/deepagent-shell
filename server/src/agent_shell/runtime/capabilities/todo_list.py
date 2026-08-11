from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware


class _DisabledTodoListMiddleware(AgentMiddleware):
    @property
    def name(self) -> str:
        return "TodoListMiddleware"


def disabled_todo_list_middleware() -> AgentMiddleware:
    """Return a same-name replacement for profile-provided Todo middleware."""

    return _DisabledTodoListMiddleware()


__all__ = ["disabled_todo_list_middleware"]
