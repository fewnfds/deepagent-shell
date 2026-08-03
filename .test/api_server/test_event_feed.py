from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from .support import *


def test_event_feed_normalizes_four_sources_and_uses_numbered_pages(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        add_api_event(client, offset=-4, body='{"message":"api"}')
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

        all_items = client.get("/api/event-feed", params=event_feed_params(page_size=100)).json()[
            "items"
        ]
        first = client.get(
            "/api/event-feed",
            params=[*EVENT_FEED_TEST_WINDOW.items(), ("page_size", "2"), ("source", "system")],
        ).json()
        second = client.get(
            "/api/event-feed",
            params=event_feed_params(page=2, page_size=2, source="system"),
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
        add_api_event(client, offset=-100, body='{"message":"keep-this-log"}')
        outside_id = add_api_event(
            client,
            offset=-100_000,
            body=json.dumps({"message": marker, "location": "outside-window"}),
        )
        for offset in range(60):
            add_api_event(
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
            params=event_feed_params(source="api_call", query="keep-this-log"),
        ).json()
        outside = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query="outside-window"),
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
            add_api_event(
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
            params=event_feed_params(source="api_call", query="boundary-window"),
        ).json()

    assert {item["id"] for item in listed["items"]} == set(ids[:2])
    assert deleted.json() == {"deleted": 2}
    assert [item["id"] for item in remaining["items"]] == [ids[2]]


def test_numbered_pages_keep_cross_source_items_with_the_same_timestamp(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamp = "2026-07-30T00:00:00.000+00:00"
    with make_client(tmp_path, monkeypatch) as client:
        api_id = add_api_event(client, offset=0, body='{"message":"api"}')
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
                *EVENT_FEED_TEST_WINDOW.items(),
                ("page_size", "1"),
                ("source", "api_call"),
                ("source", "interception"),
            ],
        ).json()
        out_of_range = client.get(
            "/api/event-feed",
            params=[
                *EVENT_FEED_TEST_WINDOW.items(),
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
                *EVENT_FEED_TEST_WINDOW.items(),
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
                params=event_feed_params(
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
