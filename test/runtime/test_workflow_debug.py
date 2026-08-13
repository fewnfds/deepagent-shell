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
from agent_shell.runtime.state import AgentShellState
from agent_shell.runtime.workflow_debug import WorkflowDebugService
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
        raw_messages = [
            {"role": "system", "content": "private-system-attention-sentinel"},
            {"role": "assistant", "content": "private-assistant-data-sentinel"},
            {"role": "user", "content": "private-user-data-sentinel"},
        ]
        context = WorkflowRuntimeContext.from_request(
            raw_messages,
            request_id="request-1",
            workflow={"id": "workflow-1", "name": "Debug Workflow"},
        )
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

        await service.start()
        try:
            run = service.create_run(
                request_id="request-1",
                workflow_id="workflow-1",
                workflow_name="Debug Workflow",
                messages_sha=context.messages_sha,
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
            assert detail["messages_sha"] == context.messages_sha
            assert detail["status"] == "completed"
            assert detail["checkpoints"]
            assert all(
                checkpoint["checkpoint_id"]
                for checkpoint in detail["checkpoints"]
            )
            assert any(
                node["kind"] == "workflow" for node in detail["run_tree"]
            )
            root = next(
                node for node in detail["run_tree"] if node["kind"] == "workflow"
            )
            assert any(
                node["parent_run_id"] == root["run_id"]
                for node in detail["run_tree"]
            )
            serialized = json.dumps(detail, ensure_ascii=False)
            assert "private-system-attention-sentinel" not in serialized
            assert "private-assistant-data-sentinel" not in serialized
            assert "private-user-data-sentinel" not in serialized

            assert await service.delete(run.thread_id) is True
            assert await service.detail(run.thread_id) is None
        finally:
            await service.close()

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
