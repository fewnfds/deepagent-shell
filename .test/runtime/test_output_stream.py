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
    normalizer = V3EventNormalizer("Primary")
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
    assert normalizer.primary_message_active is False


def test_complete_blocks_and_atomic_events_keep_v3_arrival_order() -> None:
    normalizer = V3EventNormalizer("Primary")
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
        agent_name="Primary",
        node="tools",
        message="<unsafe>",
        values={"tool_name": "commit", "status": "completed"},
    )
    tool_call = OutputEvent(
        event_type="tool_call",
        phase="end",
        sequence=2,
        timestamp="2026-01-01T00:00:01Z",
        agent_name="Primary",
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


def test_execution_yields_each_completed_semantic_event_once() -> None:
    async def scenario() -> tuple[list[str], dict[str, int]]:
        settings = config(mode="blocklist")
        settings["event_templates"]["assistant_text"] = {
            "enabled": True,
            "template": "[T]{{message}}[/T]",
        }
        settings["event_templates"]["reasoning"] = {
            "enabled": True,
            "template": "[R]{{message}}[/R]",
        }
        settings["event_templates"]["custom"] = {
            "enabled": True,
            "template": "[C]{{message}}[/C]",
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
                    "delta": {
                        "type": "reasoning-delta",
                        "reasoning": "partial",
                    },
                }
            ),
            message_envelope(
                {
                    "event": "content-block-finish",
                    "index": 0,
                    "content": {"type": "reasoning", "reasoning": "thought"},
                }
            ),
            {
                "method": "custom",
                "params": {"namespace": [], "timestamp": 2, "data": "working"},
            },
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
                    "usage": {
                        "input_tokens": 2,
                        "output_tokens": 4,
                        "total_tokens": 6,
                    },
                }
            ),
        ]
        execution = AgentExecution(
            graph=EventGraph(events),
            input_state={"messages": []},
            rectifier=OutputEventRectifier(OutputProjector(settings)),
            normalizer=V3EventNormalizer("Primary"),
        )
        parts = [part async for part in execution.stream_text()]
        return parts, execution.usage

    parts, usage = asyncio.run(scenario())

    assert parts == [
        "[R]",
        "partial",
        "[/R]",
        "[C]&quot;working&quot;[/C]",
        "[T]answer[/T]",
    ]
    assert usage == {"input_tokens": 2, "output_tokens": 4, "total_tokens": 6}


def test_model_response_observer_keeps_full_safe_source_data_per_call() -> None:
    responses = []
    normalizer = V3EventNormalizer(
        "Primary", model_response_observers=(responses.append,)
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "message-start",
                "role": "ai",
                "id": "message-1",
                "metadata": {"provider": "deepseek", "model": "reasoner"},
            }
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {"type": "reasoning", "reasoning": "full thought"},
            }
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "message-finish",
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 3,
                    "total_tokens": 10,
                    "output_token_details": {"reasoning": 2},
                },
                "metadata": {
                    "finish_reason": "length",
                    "model_name": "reasoner",
                    "system_fingerprint": "fp-1",
                    "logprobs": {"content": []},
                },
                "additional_kwargs": {"reasoning_content": "full thought"},
            }
        )
    )

    assert len(responses) == 1
    response = responses[0]
    assert response.provider_finish_reason == "length"
    assert response.finish_reason_source == "response_metadata.finish_reason"
    assert response.usage["output_token_details"] == {"reasoning": 2}
    assert response.response_metadata["system_fingerprint"] == "fp-1"
    assert response.additional_kwargs == {"reasoning_content": "full thought"}
    assert response.content_blocks == [
        {"type": "reasoning", "reasoning": "full thought"}
    ]
    assert normalizer.finish_reason == "length"


def test_last_primary_model_call_owns_external_finish_reason() -> None:
    normalizer = V3EventNormalizer("Primary")
    for run_id, reason in (("run-tools", "tool_calls"), ("run-final", "stop")):
        normalizer.feed(
            message_envelope(
                {"event": "message-start", "role": "ai", "id": run_id},
                run_id=run_id,
            )
        )
        normalizer.feed(
            message_envelope(
                {
                    "event": "message-finish",
                    "usage": {},
                    "metadata": {"finish_reason": reason},
                },
                run_id=run_id,
            )
        )

    assert normalizer.finish_reason == "stop"
    assert normalizer.finish_reason_source == "response_metadata.finish_reason"


def test_message_finish_records_the_call_without_fabricating_a_public_block_end() -> None:
    responses = []
    normalizer = V3EventNormalizer(
        "Primary", model_response_observers=(responses.append,)
    )
    normalizer.feed(
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "message-1"}
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-start",
                "index": 0,
                "content": {"type": "text", "text": ""},
            }
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-delta",
                "index": 0,
                "delta": {"type": "text-delta", "text": "partial"},
            }
        )
    )

    events = normalizer.feed(
        message_envelope(
            {
                "event": "message-finish",
                "usage": {},
                "metadata": {"finish_reason": "stop"},
            }
        )
    )

    assert events == []
    assert responses[0].stream_diagnostics["incomplete_block_count"] == 1
    assert normalizer.primary_message_active is False


def test_graph_end_discards_open_normalizer_state_without_fabricating_finish() -> None:
    normalizer = V3EventNormalizer("Primary")
    normalizer.feed(
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "message-1"}
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-start",
                "index": 0,
                "content": {"type": "reasoning", "reasoning": ""},
            }
        )
    )
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-delta",
                "index": 0,
                "delta": {"type": "reasoning-delta", "reasoning": "partial"},
            }
        )
    )

    normalizer.close_primary_messages()
    assert normalizer.finish_reason == "unknown"
    assert normalizer.primary_message_active is False


def test_message_error_fails_immediately_without_exposing_upstream_payload() -> None:
    normalizer = V3EventNormalizer("Primary")
    normalizer.feed(
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "message-1"}
        )
    )

    with pytest.raises(AgentRuntimeError) as captured:
        normalizer.feed(
            message_envelope(
                {"event": "error", "error": {"provider_body": "private"}}
            )
        )

    assert captured.value.code == "agent_execution_failed"
    assert "private" not in str(captured.value)
    assert normalizer.primary_message_active is False


def test_tool_finish_and_failure_are_complete_and_tool_delta_is_ignored() -> None:
    normalizer = V3EventNormalizer("Primary")
    normalizer.feed(
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {
                    "type": "tool_call",
                    "id": "call-1",
                    "name": "read_file",
                    "args": {"path": "README.md"},
                },
            }
        )
    )
    delta = normalizer.feed(
        {
            "method": "tools",
            "params": {
                "namespace": [],
                "timestamp": 2,
                "data": {
                    "event": "tool-output-delta",
                    "tool_call_id": "call-1",
                    "output": "partial secret",
                },
            },
        }
    )
    finished = normalizer.feed(
        {
            "method": "tools",
            "params": {
                "namespace": [],
                "timestamp": 3,
                "data": {
                    "event": "tool-finished",
                    "tool_call_id": "call-1",
                    "output": "complete result",
                },
            },
        }
    )
    failed = normalizer.feed(
        {
            "method": "tools",
            "params": {
                "namespace": [],
                "timestamp": 4,
                "data": {
                    "event": "tool-failed",
                    "tool_call_id": "call-2",
                    "tool_name": "write_file",
                    "output": {"traceback": "private"},
                },
            },
        }
    )

    assert delta == []
    assert [(event.event_type, event.phase) for event in [*finished, *failed]] == [
        ("tool_result", "end"),
        ("tool_error", "error"),
    ]
    assert finished[0].message == "complete result"
    assert finished[0].values["tool_name"] == "read_file"
    assert failed[0].message == "Tool execution failed."
    assert "private" not in repr(failed)


def test_command_tool_result_uses_only_the_matching_tool_message() -> None:
    normalizer = V3EventNormalizer("Primary")
    command = Command(
        update={
            "messages": [
                ToolMessage(content="wrong", tool_call_id="call-other"),
                ToolMessage(
                    content="final result",
                    tool_call_id="call-1",
                    name="task",
                ),
            ]
        }
    )

    events = normalizer.feed(
        {
            "method": "tools",
            "params": {
                "namespace": [],
                "timestamp": 1,
                "data": {
                    "event": "tool-finished",
                    "tool_call_id": "call-1",
                    "output": command,
                },
            },
        }
    )

    assert len(events) == 1
    assert events[0].message == "final result"
    assert events[0].values["tool_name"] == "task"
    assert "wrong" not in repr(events)


def test_subagent_model_content_stays_private_but_lifecycle_is_available() -> None:
    normalizer = V3EventNormalizer("Primary")
    internal_messages = [
        message_envelope(
            {"event": "message-start", "role": "ai", "id": "sub-message"},
            run_id="run-subagent",
            agent_name="Researcher",
            namespace=["task:research"],
        ),
        message_envelope(
            {
                "event": "content-block-start",
                "index": 0,
                "content": {"type": "text", "text": ""},
            },
            run_id="run-subagent",
            agent_name="Researcher",
            namespace=["task:research"],
        ),
        message_envelope(
            {
                "event": "content-block-delta",
                "index": 0,
                "delta": {"type": "text-delta", "text": "private draft"},
            },
            run_id="run-subagent",
            agent_name="Researcher",
            namespace=["task:research"],
        ),
        message_envelope(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {"type": "text", "text": "private answer"},
            },
            run_id="run-subagent",
            agent_name="Researcher",
            namespace=["task:research"],
        ),
        message_envelope(
            {"event": "message-finish", "usage": {}},
            run_id="run-subagent",
            agent_name="Researcher",
            namespace=["task:research"],
        ),
    ]
    lifecycle = [
        {
            "method": "lifecycle",
            "params": {
                "timestamp": 2,
                "data": {
                    "event": "started",
                    "namespace": ["task:research"],
                    "graph_name": "Researcher",
                    "cause": {"tool_call_id": "call-task"},
                },
            },
        },
        {
            "method": "lifecycle",
            "params": {
                "timestamp": 3,
                "data": {
                    "event": "completed",
                    "namespace": ["task:research"],
                },
            },
        },
    ]

    assert _normalized(normalizer, internal_messages) == []
    events = _normalized(normalizer, lifecycle)
    assert [(event.event_type, event.phase) for event in events] == [
        ("subagent", "start"),
        ("subagent", "end"),
    ]
    assert all(event.values["subagent_name"] == "Researcher" for event in events)
    assert "private" not in repr(events)


def test_unknown_internal_and_unsupported_media_events_are_not_public() -> None:
    normalizer = V3EventNormalizer("Primary")
    internal = normalizer.feed(
        {
            "method": "updates",
            "params": {"namespace": [], "data": {"secret": "private-state"}},
        }
    )
    unknown = normalizer.feed(
        {
            "method": "future-public-event",
            "params": {"namespace": [], "data": {"secret": "private-event"}},
        }
    )
    media = _normalized(
        normalizer,
        [
            message_envelope(
                {"event": "message-start", "role": "ai", "id": "message-media"}
            ),
            message_envelope(
                {
                    "event": "content-block-start",
                    "index": 0,
                    "content": {"type": "image"},
                }
            ),
            message_envelope(
                {
                    "event": "content-block-finish",
                    "index": 0,
                    "content": {
                        "type": "image",
                        "url": "https://secret.invalid/image.png",
                        "base64": "private-media",
                    },
                }
            ),
            message_envelope({"event": "message-finish", "usage": {}}),
        ],
    )

    assert internal == []
    assert unknown == []
    assert media == []
