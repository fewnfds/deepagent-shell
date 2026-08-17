from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

from deepagents.backends.utils import create_file_data
from langgraph.store.memory import InMemoryStore

from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.workflow_lifecycle import (
    LIFECYCLE_INPUT_KEY,
    lifecycle_input_namespace,
)


def _load_example() -> ModuleType:
    source = (
        Path(__file__).parents[2]
        / "examples"
        / "agent-components"
        / "custom-middleware"
        / "workflow-input-context"
        / "main.py"
    )
    spec = importlib.util.spec_from_file_location("workflow_input_context_example", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_input_context_example_applies_central_file_and_system_settings() -> None:
    module = _load_example()

    class Backend:
        async def aread(self, path, *, offset, limit):
            assert (path, offset, limit) == ("/task.md", 0, 1_000_000)
            return SimpleNamespace(
                file_data=create_file_data("attached task"),
                error=None,
            )

    module.WIC_CONFIG["attachments"] = [
        {"role": "system", "path": "/task.md", "max_chars": 8}
    ]
    module.WIC_CONFIG["convert_non_leading_system_to_user"] = True
    middleware = module.create_middleware(
        backend=Backend(),
        scope="main_agent",
        package_id="example-id",
    )
    messages = [
            {"role": "system", "content": "leading"},
            {"role": "assistant", "content": "prior"},
            {"role": "system", "content": "late"},
    ]
    context = WorkflowRuntimeContext.for_run(
        request_id="request-id",
        lifecycle_id="lifecycle-id",
        run_id="run-id",
        thread_id="thread-id",
    )
    store = InMemoryStore()
    store.put(
        lifecycle_input_namespace(context.lifecycle_id),
        LIFECYCLE_INPUT_KEY,
        {"messages": messages},
    )

    update = asyncio.run(
        middleware.abefore_agent(
            {"messages": []},
            SimpleNamespace(context=context, store=store),
        )
    )

    assert middleware.name == "WorkflowInputContextMiddleware_example-id"
    assert [(message.type, message.content) for message in update["messages"].value] == [
        ("system", "leading"),
        ("ai", "prior"),
        ("human", "late"),
        ("human", "attached"),
    ]
