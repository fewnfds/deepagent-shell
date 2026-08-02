from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from .support import *


_WIDE_WINDOW = {
    "started_at": "2000-01-01T00:00:00+00:00",
    "ended_at": "2100-01-01T00:00:00+00:00",
}


def _window_params(**values: object) -> dict[str, object]:
    return {**_WIDE_WINDOW, **values}


def _add_api_event(
    client,
    *,
    offset: int,
    body: str,
    status: str = "completed",
    response_body: str = '{"result":"ok"}',
) -> str:
    started = datetime.now(timezone.utc) + timedelta(seconds=offset)
    item = client.app.state.api_server_store.add_message_history(
        request_id=f"request-{offset}",
        model="published-model",
        agent_name="Published Primary",
        started_at=started.isoformat(timespec="milliseconds"),
        finished_at=(started + timedelta(milliseconds=10)).isoformat(
            timespec="milliseconds"
        ),
        status=status,
        request_body=body,
        response_body=response_body,
        response_content_type="application/json",
        http_status=200 if status == "completed" else 500,
        error_code=None if status == "completed" else "runtime_failed",
    )
    return str(item["id"])


def test_event_feed_normalizes_four_sources_and_uses_numbered_pages(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        _add_api_event(client, offset=-4, body='{"message":"api"}')
        client.app.state.api_server_store.add_interception_record(
            request_id="request-interception",
            model="published-model",
            agent_name="Published Primary",
            request_raw_json='{"message":"interception"}',
            model_request_raw_json='{"messages":[]}',
        )
        client.app.state.security_events.emit(
            "configuration_updated",
            {"action": "updated", "entity": "test", "entity_id": "one"},
        )
        client.app.state.runtime_diagnostics.request_started(
            request_id="request-runtime",
            model="published-model",
            agent_name="Published Primary",
        )

        all_items = client.get("/api/event-feed", params=_window_params(page_size=100)).json()[
            "items"
        ]
        first = client.get(
            "/api/event-feed",
            params=[*_WIDE_WINDOW.items(), ("page_size", "2"), ("source", "system")],
        ).json()
        second = client.get(
            "/api/event-feed",
            params=_window_params(page=2, page_size=2, source="system"),
        ).json()

    assert {item["source"] for item in all_items} == {
        "api_call",
        "interception",
        "system",
        "runtime",
    }
    assert all(
        set(item) == {
            "id",
            "source",
            "occurred_at",
            "level",
            "request_id",
            "summary",
            "inline_content",
            "matched_in_content",
            "download_available",
        }
        for item in all_items
    )
    assert all(
        json.loads(item["inline_content"])["source"] == item["source"]
        for item in all_items
        if item["inline_content"] is not None
    )
    api_item = next(item for item in all_items if item["source"] == "api_call")
    assert api_item["summary"] == "Published Primary · completed · 200"
    interception_item = next(
        item for item in all_items if item["source"] == "interception"
    )
    assert interception_item["summary"] == "Published Primary · published-model"
    runtime_item = next(item for item in all_items if item["source"] == "runtime")
    assert runtime_item["summary"] == "Published Primary · request started"
    items = [*first["items"], *second["items"]]
    assert len({(item["source"], item["id"]) for item in items}) == len(items)
    assert first["page"] == 1
    assert second["page"] == 2
    assert first["total"] == second["total"]
    assert first["total_pages"] == second["total_pages"]
    assert all(len(item["summary"]) <= 240 for item in all_items)


def test_filtered_delete_covers_unloaded_matches_across_all_sources(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "delete-every-matching-log"
    window_started = datetime.now(timezone.utc) - timedelta(hours=1)
    window_ended = datetime.now(timezone.utc) + timedelta(hours=1)
    window = {
        "started_at": window_started.isoformat(),
        "ended_at": window_ended.isoformat(),
    }
    with make_client(tmp_path, monkeypatch) as client:
        client.put(
            "/api/api-server/history/retention",
            json={"retention_limit": 100},
        )
        _add_api_event(client, offset=-100, body='{"message":"keep-this-log"}')
        outside_id = _add_api_event(
            client,
            offset=-100_000,
            body=json.dumps({"message": marker, "location": "outside-window"}),
        )
        for offset in range(60):
            _add_api_event(
                client,
                offset=offset,
                body=json.dumps({"message": marker, "offset": offset}),
            )
        client.app.state.api_server_store.add_interception_record(
            request_id="delete-interception",
            model="published-model",
            agent_name="Published Primary",
            request_raw_json=json.dumps({"message": marker}),
            model_request_raw_json='{"messages":[]}',
        )
        client.app.state.security_events.emit(
            "configuration_updated",
            {
                "action": "updated",
                "entity": "test",
                "entity_id": marker,
            },
        )
        client.app.state.runtime_diagnostics._emit(
            "info",
            request_id="delete-runtime",
            model="published-model",
            agent_name="Published Primary",
            message=marker,
        )

        first_page = client.get(
            "/api/event-feed",
            params={**window, "level": "info", "query": marker, "page_size": 50},
        ).json()
        deleted = client.post(
            "/api/event-feed/delete",
            json={**window, "source": [], "level": ["info"], "query": marker},
        )
        remaining_matches = client.get(
            "/api/event-feed",
            params={**window, "level": "info", "query": marker, "page_size": 100},
        ).json()
        retained = client.get(
            "/api/event-feed",
            params=_window_params(source="api_call", query="keep-this-log"),
        ).json()
        outside = client.get(
            "/api/event-feed",
            params=_window_params(source="api_call", query="outside-window"),
        ).json()

    assert len(first_page["items"]) == 50
    assert first_page["total"] == 63
    assert deleted.json() == {"deleted": 63}
    assert remaining_matches["items"] == []
    assert len(retained["items"]) == 1
    assert [item["id"] for item in outside["items"]] == [outside_id]


def test_list_and_delete_share_inclusive_time_boundaries(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started_at = "2026-08-01T01:00:00.000+00:00"
    ended_at = "2026-08-01T02:00:00.000+00:00"
    with make_client(tmp_path, monkeypatch) as client:
        ids = [
            _add_api_event(
                client,
                offset=index,
                body=json.dumps({"message": "boundary-window", "index": index}),
            )
            for index in range(3)
        ]
        with sqlite3.connect(
            tmp_path / "data" / "state" / "agent-shell.sqlite3"
        ) as connection:
            for item_id, timestamp in zip(
                ids,
                (started_at, ended_at, "2026-08-01T02:00:00.001+00:00"),
                strict=True,
            ):
                connection.execute(
                    "UPDATE api_message_history SET started_at = ? WHERE id = ?",
                    (timestamp, item_id),
                )
            connection.commit()

        window = {"started_at": started_at, "ended_at": ended_at}
        listed = client.get(
            "/api/event-feed",
            params={**window, "source": "api_call", "query": "boundary-window"},
        ).json()
        deleted = client.post(
            "/api/event-feed/delete",
            json={
                **window,
                "source": ["api_call"],
                "level": [],
                "query": "boundary-window",
            },
        )
        remaining = client.get(
            "/api/event-feed",
            params=_window_params(source="api_call", query="boundary-window"),
        ).json()

    assert {item["id"] for item in listed["items"]} == set(ids[:2])
    assert deleted.json() == {"deleted": 2}
    assert [item["id"] for item in remaining["items"]] == [ids[2]]


def test_numbered_pages_keep_cross_source_items_with_the_same_timestamp(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamp = "2026-07-30T00:00:00.000+00:00"
    with make_client(tmp_path, monkeypatch) as client:
        api_id = _add_api_event(client, offset=0, body='{"message":"api"}')
        interception = client.app.state.api_server_store.add_interception_record(
            request_id="same-time-interception",
            model="published-model",
            agent_name="Published Primary",
            request_raw_json='{"message":"interception"}',
            model_request_raw_json='{"messages":[]}',
        )
        with sqlite3.connect(
            tmp_path / "data" / "state" / "agent-shell.sqlite3"
        ) as connection:
            connection.execute(
                "UPDATE api_message_history SET started_at = ? WHERE id = ?",
                (timestamp, api_id),
            )
            connection.execute(
                "UPDATE interception_test_records SET intercepted_at = ? WHERE id = ?",
                (timestamp, interception["id"]),
            )
            connection.commit()

        first = client.get(
            "/api/event-feed",
            params=[
                *_WIDE_WINDOW.items(),
                ("page_size", "1"),
                ("source", "api_call"),
                ("source", "interception"),
            ],
        ).json()
        out_of_range = client.get(
            "/api/event-feed",
            params=[
                *_WIDE_WINDOW.items(),
                ("page_size", "1"),
                ("page", "3"),
                ("source", "api_call"),
                ("source", "interception"),
            ],
        ).json()
        second = client.get(
            "/api/event-feed",
            params=[
                ("page_size", "1"),
                ("page", "2"),
                *_WIDE_WINDOW.items(),
                ("source", "api_call"),
                ("source", "interception"),
            ],
        ).json()

    assert [first["items"][0]["source"], second["items"][0]["source"]] == [
        "api_call",
        "interception",
    ]
    assert first["total"] == second["total"] == 2
    assert first["total_pages"] == second["total_pages"] == 2
    assert out_of_range == {
        "items": [],
        "page": 3,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }


def test_numbered_runtime_pages_keep_every_item_in_a_same_timestamp_group(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamp = "2026-07-30T00:00:00.000+00:00"
    with make_client(tmp_path, monkeypatch) as client:
        store = client.app.state.runtime_diagnostic_store
        store.delete_entries(lambda _: True)
        for sequence in range(1, 5):
            store.add(
                timestamp=timestamp,
                level="info",
                request_id=f"same-time-{sequence}",
                model="published-model",
                agent_name="Published Primary",
                code="",
                exception_type="",
                message=f"event {sequence}",
            )

        items: list[dict[str, object]] = []
        for page in (1, 2):
            response = client.get(
                "/api/event-feed",
                params=_window_params(
                    source="runtime",
                    page_size=2,
                    page=page,
                ),
            ).json()
            items.extend(response["items"])

    keys = [(item["occurred_at"], item["id"]) for item in items]
    assert len(items) == 4
    assert len({item["id"] for item in items}) == 4
    assert keys == sorted(keys, reverse=True)


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
        item_id = _add_api_event(
            client,
            offset=0,
            body=request_body,
            response_body=response_body,
        )
        listing = client.get(
            "/api/event-feed",
            params=_window_params(source="api_call", query=marker),
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
            agent_name="Published Primary",
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
            agent_name="Published Primary",
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
            agent_name="Published Primary",
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
            agent_name="Published Primary",
            message="运" * 5000 + runtime_marker,
        )

        responses = {
            source: client.get(
                "/api/event-feed",
                params={
                    **_WIDE_WINDOW,
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


def test_event_feed_filters_short_content_and_reports_stable_errors(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        _add_api_event(client, offset=0, body='{"message":"short-visible"}')
        filtered = client.get(
            "/api/event-feed",
            params=[
                *_WIDE_WINDOW.items(),
                ("source", "api_call"),
                ("level", "info"),
                ("query", "short-visible"),
            ],
        )
        missing_window = client.get("/api/event-feed")
        inverted_window = client.get(
            "/api/event-feed",
            params={
                "started_at": "2026-08-01T01:00:00+00:00",
                "ended_at": "2026-08-01T00:00:00+00:00",
            },
        )
        naive_window = client.get(
            "/api/event-feed",
            params={
                "started_at": "2026-08-01T00:00:00",
                "ended_at": "2026-08-01T01:00:00",
            },
        )
        invalid_page_size = client.get(
            "/api/event-feed", params=_window_params(page_size=101)
        )
        invalid_level = client.get(
            "/api/event-feed", params=_window_params(level="fatal")
        )
        missing = client.get("/api/event-feed/runtime/missing/download")
        unauthenticated = client.get(
            "/api/event-feed", headers={"Authorization": "Bearer wrong"}
        )

    item = filtered.json()["items"][0]
    assert item["inline_content"] is not None
    assert json.loads(item["inline_content"])["source"] == "api_call"
    assert json.loads(item["inline_content"])["entry"]["request_body"] == (
        '{"message":"short-visible"}'
    )
    assert item["matched_in_content"] is False
    assert item["download_available"] is False
    assert missing_window.status_code == 422
    assert inverted_window.status_code == naive_window.status_code == 422
    assert inverted_window.json()["detail"]["code"] == "event_feed_time_window_invalid"
    assert naive_window.json()["detail"]["code"] == "event_feed_time_window_invalid"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "event_feed_item_not_found"
    assert unauthenticated.status_code == 401
    assert invalid_page_size.status_code == invalid_level.status_code == 422


def test_event_source_retention_limits_share_the_backend_boundary(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        api_saved = client.put(
            "/api/api-server/history/retention", json={"retention_limit": 10_000}
        )
        interception_saved = client.put(
            "/api/interception-test/records/retention",
            json={"retention_limit": 10_000},
        )
        runtime_saved = client.put(
            "/api/runtime-diagnostics/retention", json={"retention_limit": 10_000}
        )
        rejected = [
            client.put(path, json={"retention_limit": 10_001})
            for path in (
                "/api/api-server/history/retention",
                "/api/interception-test/records/retention",
                "/api/runtime-diagnostics/retention",
            )
        ]

    assert api_saved.json() == {
        "retention_limit": 10_000,
        "max_retention_limit": 10_000,
    }
    assert interception_saved.json() == {
        "retention_limit": 10_000,
        "max_retention_limit": 10_000,
    }
    assert runtime_saved.json() == {
        "verbose": False,
        "retention_limit": 10_000,
        "max_retention_limit": 10_000,
    }
    assert [response.status_code for response in rejected] == [422, 422, 422]


def test_runtime_retention_persists_entries_across_restart_and_deletes_them(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        saved = client.put(
            "/api/runtime-diagnostics/retention", json={"retention_limit": 2}
        )
        verbose_saved = client.put(
            "/api/runtime-diagnostics", json={"verbose": True}
        )
        interception_saved = client.put(
            "/api/interception-test", json={"enabled": True}
        )
        diagnostics = client.app.state.runtime_diagnostics
        for index in range(3):
            diagnostics.request_started(
                request_id=f"persisted-runtime-{index}",
                model="published-model",
                agent_name="Published Primary",
            )

    with make_client(tmp_path, monkeypatch) as restarted:
        persisted_settings = restarted.get("/api/runtime-diagnostics").json()
        persisted_interception = restarted.get("/api/interception-test").json()
        listing = restarted.get(
            "/api/event-feed",
            params=_window_params(source="runtime", page_size=100),
        ).json()
        selected = next(
            item for item in listing["items"]
            if item["request_id"] == "persisted-runtime-2"
        )
        download = restarted.get(
            f"/api/event-feed/runtime/{selected['id']}/download"
        )
        deleted = restarted.post(
            "/api/event-feed/delete",
            json={
                **_WIDE_WINDOW,
                "source": ["runtime"],
                "level": [],
                "query": "persisted-runtime-1",
            },
        )
        remaining = restarted.get(
            "/api/event-feed",
            params=_window_params(source="runtime", page_size=100),
        ).json()

    assert saved.json()["retention_limit"] == 2
    assert verbose_saved.json()["verbose"] is True
    assert persisted_settings["verbose"] is True
    assert interception_saved.json()["enabled"] is True
    assert persisted_interception["enabled"] is True
    assert {item["request_id"] for item in listing["items"]} == {
        "persisted-runtime-1",
        "persisted-runtime-2",
    }
    assert download.status_code == 200
    assert json.loads(download.content.decode("utf-8"))["entry"]["request_id"] == (
        "persisted-runtime-2"
    )
    assert deleted.json() == {"deleted": 1}
    assert [item["request_id"] for item in remaining["items"]] == [
        "persisted-runtime-2"
    ]


def test_system_log_size_setting_persists_and_has_no_backup_option(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        assert client.get("/api/event-feed/system/settings").json() == {
            "max_size_mib": 5,
            "min_size_mib": 1,
            "max_size_mib_limit": 1024,
        }
        saved = client.put(
            "/api/event-feed/system/settings",
            json={"max_size_mib": 12},
        )
        rejected_low = client.put(
            "/api/event-feed/system/settings",
            json={"max_size_mib": 0},
        )
        rejected_high = client.put(
            "/api/event-feed/system/settings",
            json={"max_size_mib": 1025},
        )

    assert saved.json() == {
        "max_size_mib": 12,
        "min_size_mib": 1,
        "max_size_mib_limit": 1024,
    }
    assert rejected_low.status_code == rejected_high.status_code == 422

    with make_client(tmp_path, monkeypatch) as restarted:
        assert restarted.get("/api/event-feed/system/settings").json()["max_size_mib"] == 12
