from __future__ import annotations

from langchain_core.messages import AIMessage

from .support import *


def _event(
    event_type: str,
    phase: str,
    *,
    sequence: int,
    stream_id: str = "",
    message: str = "",
    **values: str,
) -> OutputEvent:
    return OutputEvent(
        event_type=event_type,
        phase=phase,
        sequence=sequence,
        timestamp="2026-08-01T00:00:00Z",
        agent_name="Primary",
        node="model",
        message=message,
        values=values,
        stream_id=stream_id,
    )


def _rectifier() -> OutputEventRectifier:
    settings = config(mode="blocklist")
    settings["variable_encoding"] = "plain"
    settings["event_templates"]["reasoning"] = {
        "enabled": True,
        "template": "<reasoning>{{message}}</reasoning>",
    }
    settings["event_templates"]["assistant_text"] = {
        "enabled": True,
        "template": "<text>{{message}}</text>",
    }
    settings["event_templates"]["tool_call"] = {
        "enabled": True,
        "template": "<call id={{tool_call_id}}>{{message}}</call>",
    }
    settings["event_templates"]["tool_result"] = {
        "enabled": True,
        "template": "<result id={{tool_call_id}}>{{message}}</result>",
    }
    return OutputEventRectifier(OutputProjector(settings))


def test_competing_streams_wait_for_silence_and_never_cross_templates() -> None:
    pool = _rectifier()

    assert pool.feed(
        _event("reasoning", "start", sequence=1, stream_id="run:0"), now=0.0
    ) == ["<reasoning>"]
    assert pool.feed(
        _event(
            "reasoning",
            "delta",
            sequence=2,
            stream_id="run:0",
            message="think",
        ),
        now=0.1,
    ) == ["think"]
    assert pool.feed(
        _event("assistant_text", "start", sequence=3, stream_id="run:1"),
        now=0.2,
    ) == []
    assert pool.feed(
        _event(
            "assistant_text",
            "delta",
            sequence=4,
            stream_id="run:1",
            message="answer",
        ),
        now=0.3,
    ) == []
    assert pool.feed(
        _event(
            "reasoning",
            "end",
            sequence=5,
            stream_id="run:0",
            message="think",
        ),
        now=0.4,
    ) == []
    assert pool.expire(now=1.09) == []
    assert pool.expire(now=1.1) == ["</reasoning>", "<text>", "answer"]
    assert pool.flush() == ["</text>"]


def test_only_the_active_source_can_extend_its_silence_window() -> None:
    pool = _rectifier()
    pool.feed(_event("reasoning", "start", sequence=1, stream_id="run:0"), now=0.0)
    pool.feed(
        _event(
            "reasoning",
            "delta",
            sequence=2,
            stream_id="run:0",
            message="a",
        ),
        now=0.1,
    )
    pool.feed(
        _event("assistant_text", "start", sequence=3, stream_id="run:1"),
        now=0.2,
    )
    pool.feed(
        _event(
            "assistant_text",
            "delta",
            sequence=4,
            stream_id="run:1",
            message="queued",
        ),
        now=0.8,
    )

    assert pool.expire(now=1.1) == ["</reasoning>", "<text>", "queued"]

    pool = _rectifier()
    pool.feed(_event("reasoning", "start", sequence=1, stream_id="run:0"), now=0.0)
    pool.feed(
        _event("assistant_text", "start", sequence=2, stream_id="run:1"),
        now=0.1,
    )
    assert pool.feed(
        _event(
            "reasoning",
            "delta",
            sequence=3,
            stream_id="run:0",
            message="continued",
        ),
        now=0.9,
    ) == ["continued"]
    assert pool.expire(now=1.89) == []
    assert pool.expire(now=1.9) == ["</reasoning>", "<text>"]


def test_late_delta_after_death_gets_a_new_complete_wrapper() -> None:
    pool = _rectifier()
    parts = pool.feed(
        _event("reasoning", "start", sequence=1, stream_id="run:0"), now=0.0
    )
    parts += pool.feed(
        _event("assistant_text", "start", sequence=2, stream_id="run:1"),
        now=0.1,
    )
    parts += pool.expire(now=1.0)
    parts += pool.feed(
        _event(
            "reasoning",
            "delta",
            sequence=3,
            stream_id="run:0",
            message="late",
        ),
        now=1.1,
    )
    parts += pool.flush()

    assert "".join(parts) == (
        "<reasoning></reasoning>"
        "<text></text>"
        "<reasoning>late</reasoning>"
    )


def test_tool_call_waits_for_an_outcome_within_the_current_cycle() -> None:
    pool = _rectifier()
    pool.feed(_event("reasoning", "start", sequence=1, stream_id="run:0"), now=0.0)
    pool.feed(
        _event(
            "tool_call",
            "end",
            sequence=2,
            message='{"path":"README.md"}',
            tool_call_id="call-1",
            tool_name="read_file",
        ),
        now=0.1,
    )
    pool.feed(
        _event(
            "tool_result",
            "end",
            sequence=3,
            message="done",
            tool_call_id="call-1",
            tool_name="read_file",
        ),
        now=0.2,
    )

    assert pool.flush() == [
        "</reasoning>",
        '<call id=call-1>{"path":"README.md"}</call>',
        "<result id=call-1>done</result>",
    ]

    pool = _rectifier()
    assert pool.feed(
        _event(
            "tool_call",
            "end",
            sequence=1,
            message="args",
            tool_call_id="call-missing",
        ),
        now=0.0,
    ) == []
    assert pool.flush() == ["<call id=call-missing>args</call>"]

    pool = _rectifier()
    pool.feed(_event("reasoning", "start", sequence=1, stream_id="run:0"))
    for sequence, event_type, call_id, message in (
        (2, "tool_call", "call-a", "args-a"),
        (3, "tool_call", "call-b", "args-b"),
        (4, "tool_result", "call-b", "result-b"),
        (5, "tool_result", "call-a", "result-a"),
    ):
        pool.feed(
            _event(
                event_type,
                "end",
                sequence=sequence,
                message=message,
                tool_call_id=call_id,
                tool_name="same_tool",
            )
        )

    assert pool.flush() == [
        "</reasoning>",
        "<call id=call-a>args-a</call>",
        "<result id=call-a>result-a</result>",
        "<call id=call-b>args-b</call>",
        "<result id=call-b>result-b</result>",
    ]

    pool = _rectifier()
    for sequence, event_type, call_id, message in (
        (1, "tool_call", "call-a", "args-a"),
        (2, "tool_call", "call-b", "args-b"),
        (3, "tool_result", "call-b", "result-b"),
    ):
        assert pool.feed(
            _event(
                event_type,
                "end",
                sequence=sequence,
                message=message,
                tool_call_id=call_id,
                tool_name="same_tool",
            )
        ) == []
    assert pool.feed(
        _event(
            "tool_result",
            "end",
            sequence=4,
            message="result-a",
            tool_call_id="call-a",
            tool_name="same_tool",
        )
    ) == [
        "<call id=call-a>args-a</call>",
        "<result id=call-a>result-a</result>",
        "<call id=call-b>args-b</call>",
        "<result id=call-b>result-b</result>",
    ]


def test_pure_tool_output_does_not_require_reasoning_or_text() -> None:
    settings = config(mode="blocklist")
    settings["event_templates"]["assistant_text"]["enabled"] = False
    settings["event_templates"]["reasoning"]["enabled"] = False
    settings["event_templates"]["tool_call"] = {
        "enabled": True,
        "template": "CALL={{message}}",
    }
    settings["event_templates"]["tool_result"] = {
        "enabled": True,
        "template": "RESULT={{message}}",
    }
    pool = OutputEventRectifier(OutputProjector(settings))

    assert pool.feed(
        _event(
            "tool_call",
            "end",
            sequence=1,
            message="arguments",
            tool_call_id="call-1",
        )
    ) == []
    assert pool.feed(
        _event(
            "tool_result",
            "end",
            sequence=2,
            message="output",
            tool_call_id="call-1",
        )
    ) == ["CALL=arguments", "RESULT=output"]


def test_non_streaming_model_messages_use_the_same_tool_pairing_cycle() -> None:
    async def scenario() -> list[str]:
        settings = config(mode="blocklist")
        settings["variable_encoding"] = "plain"
        settings["event_templates"]["tool_call"] = {
            "enabled": True,
            "template": "<call id={{tool_call_id}}>{{message}}</call>",
        }
        settings["event_templates"]["tool_result"] = {
            "enabled": True,
            "template": "<result id={{tool_call_id}}>{{message}}</result>",
        }
        first_response = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "echo",
                    "args": {"value": "one"},
                    "id": "call-a",
                    "type": "tool_call",
                },
                {
                    "name": "echo",
                    "args": {"value": "two"},
                    "id": "call-b",
                    "type": "tool_call",
                },
                {
                    "name": "echo",
                    "args": {"value": "missing"},
                    "id": "call-missing",
                    "type": "tool_call",
                },
            ],
        )
        events = [
            message_envelope(first_response, run_id="nonstream-1"),
            {
                "method": "tools",
                "params": {
                    "namespace": [],
                    "timestamp": 2,
                    "data": {
                        "event": "tool-finished",
                        "tool_call_id": "call-b",
                        "output": "two",
                    },
                },
            },
            {
                "method": "tools",
                "params": {
                    "namespace": [],
                    "timestamp": 3,
                    "data": {
                        "event": "tool-finished",
                        "tool_call_id": "call-a",
                        "output": "one",
                    },
                },
            },
            message_envelope(
                AIMessage(content="done"), run_id="nonstream-2", timestamp=4
            ),
        ]
        execution = AgentExecution(
            graph=EventGraph(events),
            input_state={"messages": []},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
            automation=noop_automation(),
            media_response=noop_media_response(),
        )
        return [part async for part in execution.stream_text()]

    assert asyncio.run(scenario()) == [
        '<call id=call-a>{"value":"one"}</call>',
        "<result id=call-a>one</result>",
        '<call id=call-b>{"value":"two"}</call>',
        "<result id=call-b>two</result>",
        '<call id=call-missing>{"value":"missing"}</call>',
        "done",
    ]


def test_next_model_start_drains_compat_bridge_order_before_the_new_call() -> None:
    async def scenario() -> list[str]:
        settings = config(mode="blocklist")
        settings["variable_encoding"] = "plain"
        settings["event_templates"]["reasoning"] = {
            "enabled": True,
            "template": "<reasoning>{{message}}</reasoning>",
        }
        settings["event_templates"]["assistant_text"] = {
            "enabled": True,
            "template": "<text>{{message}}</text>",
        }
        settings["event_templates"]["tool_call"] = {
            "enabled": True,
            "template": "<call>{{message}}</call>",
        }
        settings["event_templates"]["tool_result"] = {
            "enabled": True,
            "template": "<result>{{message}}</result>",
        }
        events = [
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
                    "delta": {"type": "reasoning-delta", "reasoning": "think"},
                }
            ),
            message_envelope(
                {
                    "event": "content-block-start",
                    "index": 1,
                    "content": {"type": "text", "text": ""},
                }
            ),
            message_envelope(
                {
                    "event": "content-block-delta",
                    "index": 1,
                    "delta": {"type": "text-delta", "text": "answer"},
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
                    "index": 0,
                    "content": {"type": "reasoning", "reasoning": "think"},
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
            message_envelope(
                {
                    "event": "content-block-finish",
                    "index": 1,
                    "content": {"type": "text", "text": "answer"},
                }
            ),
            message_envelope(
                {
                    "event": "message-finish",
                    "usage": {},
                    "metadata": {"finish_reason": "stop"},
                }
            ),
            {
                "method": "tools",
                "params": {
                    "namespace": [],
                    "timestamp": 2,
                    "data": {
                        "event": "tool-finished",
                        "tool_call_id": "call-1",
                        "output": "file contents",
                    },
                },
            },
            message_envelope(
                {"event": "message-start", "role": "ai", "id": "message-2"},
                run_id="run-next",
            ),
            message_envelope(
                {"event": "message-finish", "usage": {}}, run_id="run-next"
            ),
        ]
        execution = AgentExecution(
            graph=EventGraph(events),
            input_state={"messages": []},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
            automation=noop_automation(),
            media_response=noop_media_response(),
        )
        return [part async for part in execution.stream_text()]

    assert asyncio.run(scenario()) == [
        "<reasoning>",
        "think",
        "</reasoning>",
        "<text>",
        "answer",
        "</text>",
        '<call>{"path":"README.md"}</call>',
        "<result>file contents</result>",
    ]
