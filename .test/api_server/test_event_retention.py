from __future__ import annotations

import json

from .support import *


def test_event_feed_filters_short_content_and_reports_stable_errors(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        add_api_event(client, offset=0, body='{"message":"short-visible"}')
        filtered = client.get(
            "/api/event-feed",
            params=[
                *EVENT_FEED_TEST_WINDOW.items(),
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
            "/api/event-feed", params=event_feed_params(page_size=101)
        )
        invalid_level = client.get(
            "/api/event-feed", params=event_feed_params(level="fatal")
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
            params=event_feed_params(source="runtime", page_size=100),
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
                **EVENT_FEED_TEST_WINDOW,
                "source": ["runtime"],
                "level": [],
                "query": "persisted-runtime-1",
            },
        )
        remaining = restarted.get(
            "/api/event-feed",
            params=event_feed_params(source="runtime", page_size=100),
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
