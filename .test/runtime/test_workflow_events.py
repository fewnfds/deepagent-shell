from __future__ import annotations

from langchain_core.messages import AIMessage

from agent_shell.runtime.output_event_pool import OutputEventRectifier
from agent_shell.runtime.output_projection import WorkflowOutputProjector
from agent_shell.runtime.output_stream import OutputEvent, V3EventNormalizer
from agent_shell.workflow.events import (
    WorkflowCustomEventV1,
    WorkflowEventSourceV1,
    emit_workflow_custom_event,
)

from .support import config


MAIN_A = "11111111-1111-4111-8111-111111111111"
MAIN_B = "22222222-2222-4222-8222-222222222222"
SUBAGENT = "33333333-3333-4333-8333-333333333333"
SUBAGENT_B = "44444444-4444-4444-8444-444444444444"


def _assistant_event(node_id: str, message: str, sequence: int) -> OutputEvent:
    return OutputEvent(
        event_type="assistant_text",
        phase="end",
        sequence=sequence,
        timestamp="2026-01-01T00:00:00Z",
        workflow_node_id=node_id,
        agent_profile_id=MAIN_A if node_id == "agent-a" else MAIN_B,
        message=message,
    )


def test_workflow_output_uses_the_policy_frozen_for_each_node() -> None:
    policy_a = config(mode="blocklist", template="A:{{message}}")
    policy_b = config(mode="blocklist", template="B:{{message}}")
    policy_b["variable_encoding"] = "plain"
    rectifier = OutputEventRectifier(
        WorkflowOutputProjector({"agent-a": policy_a, "agent-b": policy_b})
    )

    assert rectifier.feed(_assistant_event("agent-a", "<first>", 1)) == [
        "A:&lt;first&gt;"
    ]
    assert rectifier.feed(_assistant_event("agent-b", "<second>", 2)) == [
        "B:<second>"
    ]
    assert rectifier.feed(_assistant_event("unknown", "must stay private", 3)) == []


def test_v3_sources_keep_multiple_workflow_agents_distinct() -> None:
    normalizer = V3EventNormalizer(
        "Writer",
        workflow_sources={
            "agent-a": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-a",
                agent_profile_id=MAIN_A,
            ),
            "agent-b": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-b",
                agent_profile_id=MAIN_B,
            ),
        },
        main_agent_names=("Writer", "Reviewer"),
    )

    events = normalizer.feed(
        {
            "method": "messages",
            "params": {
                "namespace": ["agent-b:runtime-task-id"],
                "timestamp": 1,
                "data": [
                    AIMessage(content="review complete"),
                    {
                        "lc_agent_name": "Reviewer",
                        "langgraph_node": "model",
                        "run_id": "review-run",
                    },
                ],
            },
        }
    )

    output = next(item for item in events if isinstance(item, OutputEvent))
    assert output.agent_name == "Reviewer"
    assert output.workflow_node_id == "agent-b"
    assert output.agent_profile_id == MAIN_B


def test_v3_subagent_identity_is_scoped_by_workflow_node() -> None:
    normalizer = V3EventNormalizer(
        "Writer",
        workflow_sources={
            "agent-a": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-a",
                agent_profile_id=MAIN_A,
            ),
            "agent-b": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-b",
                agent_profile_id=MAIN_B,
            ),
        },
        main_agent_names=("Writer", "Reviewer"),
        workflow_subagent_profile_ids={
            "agent-a": {"Researcher": SUBAGENT},
            "agent-b": {"Researcher": SUBAGENT_B},
        },
    )

    events = normalizer.feed(
        {
            "method": "lifecycle",
            "params": {
                "timestamp": 1,
                "data": {
                    "event": "started",
                    "namespace": ["agent-b:runtime-task-id"],
                    "graph_name": "Researcher",
                    "cause": {"tool_call_id": "call-task"},
                },
            },
        }
    )

    output = next(item for item in events if isinstance(item, OutputEvent))
    assert output.workflow_node_id == "agent-b"
    assert output.agent_profile_id == MAIN_B
    assert output.subagent_profile_id == SUBAGENT_B


def test_v3_sources_distinguish_agent_subagent_and_script_nodes() -> None:
    agent_source = WorkflowEventSourceV1(
        source_type="agent",
        workflow_node_id="agent-a",
        agent_profile_id=MAIN_A,
    )
    normalizer = V3EventNormalizer(
        "Main Agent",
        workflow_sources={"agent-a": agent_source},
        subagent_profile_ids={"Researcher": SUBAGENT},
    )
    started = normalizer.feed(
        {
            "method": "lifecycle",
            "params": {
                "timestamp": 1,
                "data": {
                    "event": "started",
                    "namespace": ["agent-a:runtime-task-id"],
                    "graph_name": "Researcher",
                    "cause": {"tool_call_id": "call-task"},
                },
            },
        }
    )
    assert len(started) == 1
    subagent_event = started[0]
    assert isinstance(subagent_event, OutputEvent)
    assert subagent_event.source_type == "subagent"
    assert subagent_event.workflow_node_id == "agent-a"
    assert subagent_event.agent_profile_id == MAIN_A
    assert subagent_event.subagent_profile_id == SUBAGENT

    custom = WorkflowCustomEventV1(
        source=WorkflowEventSourceV1(
            source_type="script",
            workflow_node_id="inspect-file",
        ),
        channel="artifact.ready",
        data={"path": "/reports/result.md", "content": "finished"},
    )
    projected = normalizer.feed(
        {
            "method": "custom",
            "params": {
                "namespace": ["inspect-file:runtime-task-id"],
                "timestamp": 2,
                "data": custom.model_dump(mode="json"),
            },
        }
    )
    assert len(projected) == 1
    script_event = projected[0]
    assert isinstance(script_event, OutputEvent)
    assert script_event.source_type == "script"
    assert script_event.workflow_node_id == "inspect-file"
    assert script_event.agent_profile_id == ""
    assert script_event.values == {
        "channel": "artifact.ready",
        "data_json": '{"path":"/reports/result.md","content":"finished"}',
    }


def test_script_custom_event_passes_through_its_assigned_output_policy(
    monkeypatch,
) -> None:
    settings = config(mode="blocklist")
    settings["event_templates"]["assistant_text"]["enabled"] = False
    settings["event_templates"]["custom"] = {
        "enabled": True,
        "template": "{{source_type}}:{{channel}}:{{message}}",
    }
    normalizer = V3EventNormalizer("Main Agent")
    custom = WorkflowCustomEventV1(
        source=WorkflowEventSourceV1(
            source_type="script",
            workflow_node_id="inspect-file",
        ),
        channel="artifact.ready",
        data={"content": "finished"},
    )
    written: list[dict] = []
    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: written.append)
    emit_workflow_custom_event(custom)
    assert written == [custom.model_dump(mode="json")]

    events = normalizer.feed(
        {
            "method": "custom",
            "params": {
                "namespace": [],
                "timestamp": 1,
                "data": custom.model_dump(mode="json"),
            },
        }
    )
    rectifier = OutputEventRectifier(
        WorkflowOutputProjector({"inspect-file": settings})
    )

    assert len(events) == 1
    assert isinstance(events[0], OutputEvent)
    assert rectifier.feed(events[0]) == [
        'script:artifact.ready:{&quot;content&quot;:&quot;finished&quot;}'
    ]
