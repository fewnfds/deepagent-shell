from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from .support import *


def test_event_feed_hides_long_body_and_downloads_complete_utf8_json(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "需要下载的聊天记录"
    request_body = json.dumps(
        {
            "model": "published-model",
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": "private system prompt"},
                {"role": "user", "content": marker + "界" * 5000},
                {
                    "role": "assistant",
                    "content": "private earlier answer",
                    "tool_calls": [{"id": "private-tool-call"}],
                },
            ],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
            "private_request_field": "must not enter preview",
        },
        ensure_ascii=False,
    )
    response_body = json.dumps(
        {
            "id": "chatcmpl-preview",
            "object": "chat.completion",
            "created": 123,
            "model": "published-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "private response body",
                        "tool_calls": [{"id": "private-response-tool-call"}],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "private_usage": "must not enter preview",
            },
            "private_response_field": "must not enter preview",
        },
        ensure_ascii=False,
    )
    with make_client(tmp_path, monkeypatch) as client:
        item_id = add_api_event(
            client,
            offset=0,
            body=request_body,
            response_body=response_body,
        )
        listing = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query=marker),
        )
        item = listing.json()["items"][0]
        preview = client.get(f"/api/event-feed/api_call/{item_id}/preview")
        download = client.get(f"/api/event-feed/api_call/{item_id}/download")

    assert listing.status_code == 200
    assert item["id"] == item_id
    assert item["inline_content"] is None
    assert item["matched_in_content"] is True
    assert item["download_available"] is True
    assert "original_size_bytes" not in item
    assert marker not in listing.text
    assert preview.status_code == 200
    preview_entry = json.loads(preview.json()["content"])["entry"]
    assert preview_entry["request_id"] == "request-0"
    assert preview_entry["request_body"] == {
        "model": "published-model",
        "temperature": 0.3,
        "messages_omitted": 3,
    }
    assert preview_entry["response_body"] == {
        "id": "chatcmpl-preview",
        "object": "chat.completion",
        "created": 123,
        "model": "published-model",
        "choice_count": 1,
        "finish_reasons": ["stop"],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        },
    }
    assert marker not in preview.text
    assert "private system prompt" not in preview.text
    assert "private earlier answer" not in preview.text
    assert "private-tool-call" not in preview.text
    assert "private response body" not in preview.text
    assert "private-response-tool-call" not in preview.text
    assert "private_request_field" not in preview.text
    assert "private_response_field" not in preview.text
    assert "private_usage" not in preview.text
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert "attachment; filename=\"agent-shell-event-api_call-" in download.headers[
        "content-disposition"
    ]
    downloaded_entry = json.loads(download.content.decode("utf-8"))["entry"]
    assert downloaded_entry["request_id"] == "request-0"
    assert downloaded_entry["request_body"] == request_body
    assert downloaded_entry["response_body"] == response_body


def test_api_event_debug_download_merges_stream_chunks_without_changing_raw(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = datetime.now(timezone.utc)
    request_body = json.dumps(
        {"model": "published-model", "messages": [{"role": "user", "content": "你好"}]},
        ensure_ascii=False,
    )
    chunks = [
        {
            "id": "chatcmpl-debug",
            "object": "chat.completion.chunk",
            "created": 123,
            "model": "published-model",
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        {
            "id": "chatcmpl-debug",
            "object": "chat.completion.chunk",
            "created": 123,
            "model": "published-model",
            "choices": [{"index": 0, "delta": {"content": "你"}, "finish_reason": None}],
        },
        {
            "id": "chatcmpl-debug",
            "object": "chat.completion.chunk",
            "created": 123,
            "model": "published-model",
            "choices": [{"index": 0, "delta": {"content": "好"}, "finish_reason": None}],
        },
        {
            "id": "chatcmpl-debug",
            "object": "chat.completion.chunk",
            "created": 123,
            "model": "published-model",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "agent_shell": {"termination": {"source": "provider", "reason": "stop"}},
        },
    ]
    response_body = "".join(
        "data: " + json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n\n"
        for chunk in chunks
    ) + "data: [DONE]\n\n"

    with make_client(tmp_path, monkeypatch) as client:
        item = client.app.state.api_server_store.add_message_history(
            request_id="request-debug-stream",
            model="published-model",
            agent_name="Published Main Agent",
            started_at=started.isoformat(timespec="milliseconds"),
            finished_at=(started + timedelta(seconds=1)).isoformat(timespec="milliseconds"),
            status="completed",
            request_body=request_body,
            response_body=response_body,
            response_content_type="text/event-stream",
            http_status=200,
            error_code=None,
        )
        item_id = str(item["id"])
        client.app.state.runtime_diagnostic_store.add(
            timestamp=(started + timedelta(milliseconds=500)).isoformat(
                timespec="milliseconds"
            ),
            level="error",
            request_id="request-debug-stream",
            model="published-model",
            agent_name="Published Main Agent",
            code="provider_request_failed",
            exception_type="AgentRuntimeError",
            message="request failed\n\nSanitized traceback:\n  safe/module.py:1 in call",
        )
        raw = client.get(f"/api/event-feed/api_call/{item_id}/download")
        debug = client.get(
            f"/api/event-feed/api_call/{item_id}/download",
            params={"view": "debug"},
        )
        preview = client.get(f"/api/event-feed/api_call/{item_id}/preview")
        invalid = client.get(
            f"/api/event-feed/api_call/{item_id}/download",
            params={"view": "compact"},
        )

    raw_entry = json.loads(raw.content.decode("utf-8"))["entry"]
    debug_entry = json.loads(debug.content.decode("utf-8"))["entry"]
    preview_entry = json.loads(preview.json()["content"])["entry"]
    merged = debug_entry["response_body"]
    assert raw_entry["request_body"] == request_body
    assert raw_entry["response_body"] == response_body
    assert "runtime_diagnostics" not in raw_entry
    assert debug_entry["request_body"] == json.loads(request_body)
    assert debug_entry["runtime_diagnostics"][0]["code"] == "provider_request_failed"
    assert "Sanitized traceback" in debug_entry["runtime_diagnostics"][0]["message"]
    assert merged == {
        "chunk_count": 4,
        "content": "你好",
        "created": 123,
        "done": True,
        "error": None,
        "finish_reason": "stop",
        "id": "chatcmpl-debug",
        "model": "published-model",
        "object": "chat.completion.debug",
        "role": "assistant",
        "streamed": True,
        "termination": {"reason": "stop", "source": "provider"},
        "usage": {"completion_tokens": 2, "prompt_tokens": 10, "total_tokens": 12},
    }
    assert preview_entry["request_body"] == {
        "model": "published-model",
        "messages_omitted": 1,
    }
    assert preview_entry["response_body"] == {
        "object": "chat.completion.debug",
        "streamed": True,
        "chunk_count": 4,
        "done": True,
        "id": "chatcmpl-debug",
        "created": 123,
        "model": "published-model",
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        },
        "termination": {"source": "provider", "reason": "stop"},
    }
    assert "你好" not in preview.text
    assert debug.headers["content-disposition"].endswith('-debug.json"')
    assert invalid.status_code == 422


def test_other_event_sources_download_long_public_records(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    system_marker = "SYSTEM-HIDDEN-MARKER"
    runtime_marker = "RUNTIME-HIDDEN-MARKER"
    with make_client(tmp_path, monkeypatch) as client:
        interception = client.app.state.api_server_store.add_interception_record(
            request_id="long-interception",
            model="published-model",
            agent_name="Published Main Agent",
            request_raw_json='{"message":"' + "拦" * 5000 + '"}',
            model_request_raw_json='{"messages":[]}',
        )
        client.app.state.security_events.emit(
            "configuration_updated",
            {
                "action": "updated",
                "entity": "test",
                "entity_id": "系" * 5000 + system_marker,
            },
        )
        client.app.state.runtime_diagnostics._emit(
            "info",
            request_id="long-runtime",
            model="published-model",
            agent_name="Published Main Agent",
            message="运" * 5000 + runtime_marker,
        )

        responses = {
            source: client.get(
                "/api/event-feed",
                params={
                    **EVENT_FEED_TEST_WINDOW,
                    "source": source,
                    "page_size": 100,
                    **(
                        {"query": system_marker}
                        if source == "system"
                        else {"query": runtime_marker}
                        if source == "runtime"
                        else {}
                    ),
                },
            )
            for source in ("interception", "system", "runtime")
        }
        listings = {source: response.json()["items"] for source, response in responses.items()}
        selected = {
            "interception": next(
                item for item in listings["interception"]
                if item["id"] == interception["id"]
            ),
            "system": next(
                item for item in listings["system"]
                if item["download_available"]
            ),
            "runtime": next(
                item for item in listings["runtime"]
                if item["request_id"] == "long-runtime"
            ),
        }
        downloads = {
            source: client.get(
                f"/api/event-feed/{source}/{item['id']}/download"
            )
            for source, item in selected.items()
        }

    assert all(item["inline_content"] is None for item in selected.values())
    assert all(item["download_available"] for item in selected.values())
    assert selected["system"]["matched_in_content"] is True
    assert selected["runtime"]["matched_in_content"] is True
    assert system_marker not in responses["system"].text
    assert runtime_marker not in responses["runtime"].text
    assert all(response.status_code == 200 for response in downloads.values())
    assert all(json.loads(response.content.decode("utf-8"))["source"] == source
               for source, response in downloads.items())
