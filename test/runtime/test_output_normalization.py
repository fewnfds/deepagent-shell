from __future__ import annotations

from .support import *


def _normalized(
    normalizer: V3EventNormalizer, envelopes: list[dict]
) -> list[OutputEvent]:
    return [
        event
        for envelope in envelopes
        for event in normalizer.feed(envelope)
        if isinstance(event, OutputEvent)
    ]


def test_text_stream_keeps_v3_start_delta_finish_boundaries_without_rewriting() -> None:
    normalizer = V3EventNormalizer("Main Agent")
    envelopes = [
        {
            "method": "values",
            "params": {
                "namespace": [],
                "timestamp": 1,
                "data": {"messages": ["private state"]},
            },
        },
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "message-1"},
            timestamp=1_000,
        ),
        message_envelope(
            {
                "event": "content-block-start",
                "index": 0,
                "content": {"type": "text", "text": ""},
            },
            timestamp=2_000,
        ),
        *[
            message_envelope(
                {
                    "event": "content-block-delta",
                    "index": 0,
                    "delta": {
                        "type": "text-delta",
                        "text": f"partial-{index}",
                    },
                },
                timestamp=3_000 + index,
            )
            for index in range(100)
        ],
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {"type": "text", "text": "<complete answer>"},
            },
            timestamp=9_000,
        ),
        message_envelope(
            {
                "event": "message-finish",
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 3,
                    "total_tokens": 10,
                    "output_token_details": {"reasoning": 2},
                },
            },
            timestamp=10_000,
        ),
    ]

    events = _normalized(normalizer, envelopes)

    assert [(event.event_type, event.phase) for event in events] == [
        ("assistant_text", "start"),
        *[("assistant_text", "delta") for _ in range(100)],
        ("assistant_text", "end"),
    ]
    assert events[0].timestamp == "1970-01-01T00:00:02.000Z"
    assert events[-1].timestamp == "1970-01-01T00:00:09.000Z"
    assert events[-1].message == "<complete answer>"
    assert "partial-0" in repr(events)
    assert "private state" not in repr(events)
    assert normalizer.usage == {
        "input_tokens": 7,
        "output_tokens": 3,
        "total_tokens": 10,
        "reasoning_tokens": 2,
    }
    assert normalizer.main_agent_message_active is False


def test_complete_blocks_and_atomic_events_keep_v3_arrival_order() -> None:
    normalizer = V3EventNormalizer("Main Agent")
    envelopes = [
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "message-1"}
        ),
        message_envelope(
            {
                "event": "content-block-start",
                "index": 0,
                "content": {"type": "reasoning", "reasoning": ""},
            }
        ),
        message_envelope(
            {
                "event": "content-block-delta",
                "index": 0,
                "delta": {"type": "reasoning-delta", "reasoning": "draft"},
            }
        ),
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {"type": "reasoning", "reasoning": "final thought"},
            }
        ),
        {
            "method": "custom:progress",
            "params": {
                "namespace": [],
                "timestamp": 2,
                "data": {"status": "ready"},
            },
        },
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 1,
                "content": {"type": "text", "text": "final answer"},
            }
        ),
        message_envelope(
            {
                "event": "content-block-start",
                "index": 2,
                "content": {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "read_file",
                    "args": {},
                },
            }
        ),
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 2,
                "content": {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "read_file",
                    "args": {"path": "README.md"},
                },
            }
        ),
        message_envelope({"event": "message-finish", "usage": {}}),
    ]

    events = _normalized(normalizer, envelopes)

    assert [(event.event_type, event.phase) for event in events] == [
        ("reasoning", "start"),
        ("reasoning", "delta"),
        ("reasoning", "end"),
        ("custom", "end"),
        ("assistant_text", "end"),
        ("tool_call", "start"),
        ("tool_call", "end"),
    ]
    assert [event.message for event in events] == [
        "",
        "draft",
        "final thought",
        '{"status":"ready"}',
        "final answer",
        "{}",
        '{"path":"README.md"}',
    ]
    assert events[3].values == {
        "channel": "progress",
        "data_json": '{"status":"ready"}',
    }
    assert events[6].values["arguments"] == '{"path":"README.md"}'


def test_projector_uses_one_template_and_exact_optional_event_scope() -> None:
    tool_result = OutputEvent(
        event_type="tool_result",
        phase="end",
        sequence=1,
        timestamp="2026-01-01T00:00:00Z",
        agent_name="Main Agent",
        node="tools",
        message="<unsafe>",
        values={"tool_name": "commit", "status": "completed"},
    )
    tool_call = OutputEvent(
        event_type="tool_call",
        phase="end",
        sequence=2,
        timestamp="2026-01-01T00:00:01Z",
        agent_name="Main Agent",
        node="tools",
        message="call",
        values={"tool_name": "commit"},
    )

    scoped_settings = config(
        mode="allowlist",
        mappings=[{"field": "tool_result.tool_name", "value": "commit"}],
    )
    scoped_settings["event_templates"]["assistant_text"]["enabled"] = False
    scoped_settings["event_templates"]["tool_result"]["enabled"] = True
    scoped_settings["event_templates"]["tool_call"]["enabled"] = True
    unscoped_settings = config(
        mode="allowlist",
        mappings=[{"field": "tool_name", "value": "commit"}],
    )
    unscoped_settings["event_templates"]["assistant_text"]["enabled"] = False
    unscoped_settings["event_templates"]["tool_result"]["enabled"] = True
    unscoped_settings["event_templates"]["tool_call"]["enabled"] = True
    blocklist_settings = config(
        mode="blocklist",
        mappings=[{"field": "tool_result.tool_name", "value": "commit"}],
    )
    blocklist_settings["event_templates"]["assistant_text"]["enabled"] = False
    blocklist_settings["event_templates"]["tool_result"]["enabled"] = True
    blocklist_settings["event_templates"]["tool_call"]["enabled"] = True

    scoped = OutputProjector(scoped_settings)
    unscoped = OutputProjector(unscoped_settings)
    blocklist = OutputProjector(blocklist_settings)

    assert scoped.render(tool_result) == "&lt;unsafe&gt;"
    assert scoped.render(tool_call) == ""
    assert unscoped.render(tool_result) == "&lt;unsafe&gt;"
    assert unscoped.render(tool_call) == "call"
    assert blocklist.render(tool_result) == ""
    assert blocklist.render(tool_call) == "call"
