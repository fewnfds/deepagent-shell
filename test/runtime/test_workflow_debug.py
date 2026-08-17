from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.app import create_app
from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.input_messages import client_messages_sha
from agent_shell.runtime.state import AgentShellState
from agent_shell.runtime.workflow_debug import WorkflowDebugService
from agent_shell.runtime.workflow_lifecycle import (
    LIFECYCLE_INPUT_KEY,
    WorkflowLifecycleService,
    lifecycle_input_namespace,
)
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.file_config import FileConfigRepository
from agent_shell.storage.history_retention import HistoryRetentionStore
from agent_shell.storage.workflow_runs import WorkflowRunStore
from agent_shell.workflow import admit_workflow_document, compile_workflow
from support import ScopedAuthTestClient, configure_scope_tokens


AGENT_ID = "11111111-1111-4111-8111-111111111111"


class _MiddlewareRuntime:
    async def close(self) -> None:
        return None


def test_workflow_debug_retention_never_prunes_running_runs(tmp_path) -> None:
    data_root = tmp_path / "data"
    database = SQLiteDatabase(data_root / "state" / "agent-shell.sqlite3")
    configuration = FileConfigRepository(data_root)
    retention = HistoryRetentionStore(configuration)
    retention.set_limit("workflow_debug_history", 1)
    store = WorkflowRunStore(database, retention)

    def begin(thread_id: str, started_at: str) -> None:
        store.begin(
            {
                "thread_id": thread_id,
                "run_id": f"run-{thread_id}",
                "request_id": "request",
                "workflow_id": "workflow",
                "workflow_name": "Workflow",
                "messages_sha": "a" * 64,
                "started_at": started_at,
                "langsmith_project": "test",
                "tracing_enabled": False,
                "run_tree": [],
            }
        )

    begin("running", "2026-01-01T00:00:00.000+00:00")
    begin("old-terminal", "2026-01-01T00:00:01.000+00:00")
    store.finish(
        thread_id="old-terminal",
        status="completed",
        finished_at="2026-01-01T00:00:02.000+00:00",
        error_code="",
        run_tree=[],
    )
    begin("new-terminal", "2026-01-01T00:00:03.000+00:00")
    store.finish(
        thread_id="new-terminal",
        status="completed",
        finished_at="2026-01-01T00:00:04.000+00:00",
        error_code="",
        run_tree=[],
    )

    assert store.get("running")["status"] == "running"  # type: ignore[index]
    assert store.get("old-terminal") is None
    assert store.get("new-terminal")["status"] == "completed"  # type: ignore[index]


def test_workflow_debug_retention_update_prunes_only_terminal_index(tmp_path) -> None:
    data_root = tmp_path / "data"
    database = SQLiteDatabase(data_root / "state" / "agent-shell.sqlite3")
    configuration = FileConfigRepository(data_root)
    store = WorkflowRunStore(database, HistoryRetentionStore(configuration))

    for index in range(3):
        thread_id = f"terminal-{index}"
        store.begin(
            {
                "thread_id": thread_id,
                "run_id": f"run-{index}",
                "request_id": "request",
                "workflow_id": "workflow",
                "workflow_name": "Workflow",
                "messages_sha": "a" * 64,
                "started_at": f"2026-01-01T00:00:0{index}.000+00:00",
                "langsmith_project": "test",
                "tracing_enabled": False,
                "run_tree": [],
            }
        )
        store.finish(
            thread_id=thread_id,
            status="completed",
            finished_at=f"2026-01-01T00:00:1{index}.000+00:00",
            error_code="",
            run_tree=[],
        )

    assert store.set_retention(1)["retention_limit"] == 1
    assert [item["thread_id"] for item in store.list(limit=10)] == ["terminal-2"]


def _workflow_payload() -> dict[str, object]:
    return {
        "definition": {
            "schema_version": 1,
            "state_contract": "agent-shell.workflow.agent-invocations.v1",
            "nodes": [
                {"id": "start", "type": "start", "type_version": 1, "config": {}},
                {
                    "id": "agent-1",
                    "type": "agent",
                    "type_version": 1,
                    "config": {"main_agent_id": AGENT_ID},
                },
                {"id": "end", "type": "end", "type_version": 1, "config": {}},
            ],
            "edges": [
                {
                    "id": "start-agent",
                    "source": "start",
                    "source_handle": "next",
                    "target": "agent-1",
                    "target_handle": "in",
                },
                {
                    "id": "agent-end",
                    "source": "agent-1",
                    "source_handle": "next",
                    "target": "end",
                    "target_handle": "in",
                },
            ],
        },
        "layout": {
            "nodes": {
                "start": {"x": 0, "y": 0},
                "agent-1": {"x": 240, "y": 0},
                "end": {"x": 480, "y": 0},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }


def test_workflow_debug_persists_official_checkpoints_without_turning_input_into_chat_state(
    tmp_path,
) -> None:
    async def scenario() -> None:
        data_root = tmp_path / "data"
        database = SQLiteDatabase(data_root / "state" / "agent-shell.sqlite3")
        configuration = FileConfigRepository(data_root)
        HistoryRetentionStore(configuration).set_limit(
            "workflow_debug_history", 1
        )
        store = WorkflowRunStore(
            database,
            HistoryRetentionStore(configuration),
        )
        service = WorkflowDebugService(
            database.path,
            store,
            tracing_enabled=False,
            langsmith_project="workflow-debug-test",
        )
        lifecycle = WorkflowLifecycleService(database.path)
        raw_messages = [
            {"role": "system", "content": "private-system-attention-sentinel"},
            {"role": "assistant", "content": "private-assistant-data-sentinel"},
            {"role": "user", "content": "private-user-data-sentinel"},
        ]
        messages_sha = client_messages_sha(raw_messages)
        observed_root_messages: list[object] = []

        def inspect_state(state: AgentShellState) -> dict[str, object]:
            observed_root_messages.extend(state.get("messages", []))
            return {
                "messages": [AIMessage(content="complete")],
                "shared_vars": {"result": "complete"},
            }

        agent_graph = (
            StateGraph(AgentShellState, context_schema=WorkflowRuntimeContext)
            .add_node("inspect", inspect_state)
            .add_edge(START, "inspect")
            .add_edge("inspect", END)
            .compile()
        )
        admission, document = admit_workflow_document(_workflow_payload())
        assert admission.valid is True
        assert document is not None

        await lifecycle.start()
        await service.start()
        try:
            run = service.create_run(
                request_id="request-1",
                workflow_id="workflow-1",
                workflow_name="Debug Workflow",
                messages_sha=messages_sha,
            )
            lifecycle_id = await lifecycle.create(
                raw_messages,
                request_id="request-1",
                run_id=str(run.run_id),
                thread_id=run.thread_id,
                workflow_id="workflow-1",
                workflow_name="Debug Workflow",
            )
            context = WorkflowRuntimeContext.for_run(
                request_id="request-1",
                lifecycle_id=lifecycle_id,
                run_id=str(run.run_id),
                thread_id=run.thread_id,
                workflow={"id": "workflow-1", "name": "Debug Workflow"},
            )
            run.begin()
            graph = compile_workflow(
                document,
                node_agents={
                    "agent-1": BuiltAgent(
                        graph=agent_graph,
                        input_state={"messages": [], "shared_vars": {}},
                        output_config={},
                        agent_id=AGENT_ID,
                        agent_name="Debug Agent",
                        subagent_profile_ids={},
                        middleware_runtime=_MiddlewareRuntime(),  # type: ignore[arg-type]
                    )
                },
                checkpointer=service.checkpointer,
                store=lifecycle.store,
            )

            result = await graph.ainvoke(
                {"shared_vars": {}, "agent_invocations": {}},
                config=run.config(),
                context=context,
                durability="sync",
            )
            await run.finish("completed")

            assert result["shared_vars"] == {"result": "complete"}
            assert observed_root_messages == []
            detail = await service.detail(run.thread_id)
            assert detail is not None
            assert detail["messages_sha"] == messages_sha
            assert detail["status"] == "completed"
            assert detail["checkpoints"]
            assert all(
                checkpoint["checkpoint_id"]
                for checkpoint in detail["checkpoints"]
            )
            workflow_roots = [
                node for node in detail["run_tree"] if node["kind"] == "workflow"
            ]
            assert len(workflow_roots) == 1
            root = workflow_roots[0]
            assert root["run_id"] == str(run.run_id)
            assert root["parent_run_id"] is None
            assert root["name"] == "Debug Workflow"
            assert any(
                node["parent_run_id"] == root["run_id"]
                for node in detail["run_tree"]
            )
            serialized = json.dumps(detail, ensure_ascii=False)
            assert "private-system-attention-sentinel" not in serialized
            assert "private-assistant-data-sentinel" not in serialized
            assert "private-user-data-sentinel" not in serialized

            lifecycle_input = await lifecycle.store.aget(
                lifecycle_input_namespace(lifecycle_id),
                LIFECYCLE_INPUT_KEY,
            )
            assert lifecycle_input is not None
            assert lifecycle_input.value["messages"] == raw_messages
            assert lifecycle_input.value["messages_sha"] == messages_sha

            newer = service.create_run(
                request_id="request-2",
                workflow_id="workflow-1",
                workflow_name="Newer Debug Workflow",
                messages_sha="b" * 64,
            )
            newer.begin()
            await newer.finish("completed")

            assert await service.detail(run.thread_id) is None
            assert await service.checkpoint_count(run.thread_id) > 0
            assert await service.purge_thread(run.thread_id) is False
            assert await service.checkpoint_count(run.thread_id) == 0
        finally:
            await service.close()
            await lifecycle.close()

    asyncio.run(scenario())


def test_workflow_debug_management_api_lists_details_and_deletes_runs(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    configure_scope_tokens(monkeypatch, tmp_path)
    app = create_app()

    with ScopedAuthTestClient(app) as client:
        run = app.state.workflow_debug.create_run(
            request_id="request-api",
            workflow_id="workflow-api",
            workflow_name="API Debug Workflow",
            messages_sha="a" * 64,
        )
        run.begin()

        listing = client.get("/api/workflow-debug/runs")
        assert listing.status_code == 200
        assert [item["thread_id"] for item in listing.json()["items"]] == [
            run.thread_id
        ]

        detail = client.get(f"/api/workflow-debug/runs/{run.thread_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "running"
        assert detail.json()["checkpoints"] == []

        active_delete = client.delete(
            f"/api/workflow-debug/runs/{run.thread_id}"
        )
        assert active_delete.status_code == 409
        app.state.workflow_debug.store.finish(
            thread_id=run.thread_id,
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            error_code="",
            run_tree=run.collector.snapshot(),
        )

        deleted = client.delete(f"/api/workflow-debug/runs/{run.thread_id}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}
        assert client.get(
            f"/api/workflow-debug/runs/{run.thread_id}"
        ).status_code == 404
