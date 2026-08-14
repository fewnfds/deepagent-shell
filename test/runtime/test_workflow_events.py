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


def _workflow_output_config(
    event_name: str,
    source: str = 'def output(event):\n    return event["message"]\n',
) -> dict:
    return {
        "event_outputs": {
            event_name: {"enabled": True, "output_source": source}
        }
    }


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
    policy_a = config(
        mode="blocklist",
        source='def output(event):\n    return "A:" + event["message"]\n',
    )
    policy_b = config(
        mode="blocklist",
        source='def output(event):\n    return "B:" + event["message"]\n',
    )
    rectifier = OutputEventRectifier(
        WorkflowOutputProjector({"agent-a": policy_a, "agent-b": policy_b})
    )

    assert rectifier.feed(_assistant_event("agent-a", "<first>", 1)) == [
        "A:<first>"
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


def test_v3_namespace_resolves_agent_without_lc_agent_name_and_keeps_raw_order() -> None:
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
        workflow_agent_names={"agent-a": "Writer", "agent-b": "Reviewer"},
    )

    events = normalizer.feed(
        {
            "seq": 17,
            "method": "messages",
            "params": {
                "namespace": ["agent-b:invocation-2", "model:model-run"],
                "timestamp": 1,
                "data": [
                    AIMessage(content="review complete"),
                    {"langgraph_node": "model", "run_id": "review-run"},
                ],
            },
        }
    )

    boundary = events[0]
    output = next(item for item in events if isinstance(item, OutputEvent))
    assert boundary.source_key == output.source_key
    assert boundary.cycle_key == output.cycle_key == "agent-b:invocation-2"
    assert boundary.raw_seq == output.raw_seq == 17
    assert output.agent_name == "Reviewer"
    assert output.workflow_node_id == "agent-b"

    unknown = normalizer.feed(
        {
            "seq": 18,
            "method": "messages",
            "params": {
                "namespace": ["unknown:invocation"],
                "data": [
                    AIMessage(content="must stay private"),
                    {"langgraph_node": "model", "run_id": "unknown-run"},
                ],
            },
        }
    )
    assert len(unknown) == 1
    assert isinstance(unknown[0], OutputEvent)
    assert unknown[0].source_type == "non_agent"


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
    assert output.event_type == "subagent"


def test_tool_name_cache_is_scoped_by_workflow_source_and_invocation() -> None:
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
        workflow_agent_names={"agent-a": "Writer", "agent-b": "Reviewer"},
    )

    for node_id, tool_name in (("agent-a", "read_file"), ("agent-b", "search")):
        normalizer.feed(
            {
                "method": "messages",
                "params": {
                    "namespace": [f"{node_id}:invocation", "model:model-run"],
                    "data": [
                        {
                            "event": "content-block-finish",
                            "index": 0,
                            "content": {
                                "type": "tool_call",
                                "id": "shared-call",
                                "name": tool_name,
                                "args": {},
                            },
                        },
                        {"langgraph_node": "model", "run_id": f"run-{node_id}"},
                    ],
                },
            }
        )

    results = []
    for node_id in ("agent-b", "agent-a"):
        results.extend(
            normalizer.feed(
                {
                    "method": "tools",
                    "params": {
                        "namespace": [f"{node_id}:invocation", "tools:tool-run"],
                        "data": {
                            "event": "tool-finished",
                            "tool_call_id": "shared-call",
                            "output": f"{node_id} result",
                        },
                    },
                }
            )
        )

    assert [event.values["tool_name"] for event in results] == [
        "search",
        "read_file",
    ]


def test_v3_sources_distinguish_agent_subagent_and_script_nodes() -> None:
    agent_source = WorkflowEventSourceV1(
        source_type="agent",
        workflow_node_id="agent-a",
        agent_profile_id=MAIN_A,
    )
    normalizer = V3EventNormalizer(
        "Main Agent",
        workflow_sources={
            "agent-a": agent_source,
            "inspect-file": WorkflowEventSourceV1(
                source_type="script",
                workflow_node_id="inspect-file",
            ),
        },
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


def test_script_custom_event_requires_the_workflow_event_output_component(
    monkeypatch,
) -> None:
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
    blocked = OutputEventRectifier(WorkflowOutputProjector({}))
    allowed = OutputEventRectifier(
        WorkflowOutputProjector(
            {}, workflow_output_config=_workflow_output_config("custom")
        )
    )

    assert len(events) == 1
    assert isinstance(events[0], OutputEvent)
    assert blocked.feed(events[0]) == []
    assert allowed.feed(events[0]) == ['{"content":"finished"}']


def test_registered_script_custom_event_uses_the_workflow_component_script() -> None:
    source = WorkflowEventSourceV1(
        source_type="script",
        workflow_node_id="inspect-file",
    )
    normalizer = V3EventNormalizer(
        "Main Agent",
        workflow_sources={"inspect-file": source},
    )
    custom = WorkflowCustomEventV1(
        source=source,
        channel="artifact.ready",
        data={"content": "finished"},
    )
    events = normalizer.feed(
        {
            "method": "custom",
            "params": {
                "namespace": ["inspect-file:invocation"],
                "data": custom.model_dump(mode="json"),
            },
        }
    )
    rectifier = OutputEventRectifier(
        WorkflowOutputProjector(
            {}, workflow_output_config=_workflow_output_config("custom")
        )
    )

    assert rectifier.feed(events[0]) == ['{"content":"finished"}']

    unregistered = normalizer.feed(
        {
            "method": "custom",
            "params": {
                "namespace": ["unknown:invocation"],
                "data": custom.model_dump(mode="json"),
            },
        }
    )
    assert len(unregistered) == 1
    assert isinstance(unregistered[0], OutputEvent)
    assert unregistered[0].source_type == "non_agent"


def test_workflow_event_output_script_selects_and_renders_non_agent_events() -> None:
    event = OutputEvent(
        event_type="custom",
        phase="end",
        sequence=1,
        timestamp="2026-01-01T00:00:00Z",
        source_type="non_agent",
        message="visible",
        workflow_event_kind="custom",
        values={"channel": "progress"},
    )
    blocked = OutputEventRectifier(
        WorkflowOutputProjector({}, workflow_output_config=_workflow_output_config("values"))
    )
    allowed = OutputEventRectifier(
        WorkflowOutputProjector(
            {},
            workflow_output_config=_workflow_output_config(
                "custom",
                'def output(event):\n    return event["channel"] + ":" + event["message"]\n',
            ),
        )
    )

    assert blocked.feed(event) == []
    assert allowed.feed(event) == ["progress:visible"]


def test_non_agent_raw_channels_default_to_string_while_agent_state_stays_internal() -> None:
    normalizer = V3EventNormalizer(
        "Writer",
        workflow_sources={
            "agent-a": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-a",
                agent_profile_id=MAIN_A,
            )
        },
        workflow_agent_names={"agent-a": "Writer"},
    )

    agent_state = normalizer.feed(
        {
            "method": "updates",
            "params": {
                "namespace": ["agent-a:invocation"],
                "data": {"messages": "private agent state"},
            },
        }
    )
    script_output = normalizer.feed(
        {
            "method": "updates",
            "params": {
                "namespace": ["script-node:invocation"],
                "data": {"result": "ready"},
            },
        }
    )
    rectifier = OutputEventRectifier(WorkflowOutputProjector({}))

    assert agent_state == []
    assert len(script_output) == 1
    assert isinstance(script_output[0], OutputEvent)
    assert script_output[0].source_type == "non_agent"
    assert script_output[0].source_key == "unknown|script-node:invocation"
    assert rectifier.feed(script_output[0]) == []
    configured = OutputEventRectifier(
        WorkflowOutputProjector(
            {},
            workflow_output_config={
                "event_outputs": {
                    "updates": {
                        "enabled": True,
                        "output_source": (
                            'def output(event):\n'
                            '    return event["data"]["result"]\n'
                        ),
                    }
                }
            },
        )
    )
    assert configured.feed(script_output[0]) == ["ready"]


def test_workflow_event_output_script_receives_the_full_state_dict() -> None:
    values = OutputEvent(
        event_type="custom",
        phase="end",
        sequence=1,
        timestamp="2026-01-01T00:00:00Z",
        source_type="non_agent",
        workflow_event_kind="values",
        data={"shared_vars": {"answer": 42}},
    )
    projector = WorkflowOutputProjector(
        {},
        workflow_output_config={
            "event_outputs": {
                "values": {
                    "enabled": True,
                    "output_source": (
                        'def output(event):\n'
                        '    return str(event["data"]["shared_vars"]["answer"])\n'
                    ),
                }
            }
        },
    )

    assert projector.render(values) == "42"


def test_v3_marks_only_the_full_state_channel_for_filtering() -> None:
    normalizer = V3EventNormalizer(
        "Writer",
        workflow_sources={
            "agent-a": WorkflowEventSourceV1(
                source_type="agent",
                workflow_node_id="agent-a",
                agent_profile_id=MAIN_A,
            )
        },
    )

    values = normalizer.feed(
        {
            "method": "values",
            "params": {
                "namespace": ["script-node:invocation"],
                "data": {"result": "ready"},
            },
        }
    )
    updates = normalizer.feed(
        {
            "method": "updates",
            "params": {
                "namespace": ["script-node:invocation"],
                "data": {"result": "ready"},
            },
        }
    )
    custom = normalizer.feed(
        {
            "method": "custom:progress",
            "params": {
                "namespace": ["script-node:invocation"],
                "data": {"result": "ready"},
            },
        }
    )

    assert len(values) == len(updates) == len(custom) == 1
    assert isinstance(values[0], OutputEvent)
    assert isinstance(updates[0], OutputEvent)
    assert isinstance(custom[0], OutputEvent)
    assert values[0].workflow_event_kind == "values"
    assert updates[0].workflow_event_kind == "updates"
    assert custom[0].workflow_event_kind == "custom"
