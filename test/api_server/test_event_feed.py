from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from .support import *


def test_event_feed_exposes_only_supported_sources(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        interception = client.app.state.api_server_store.add_interception_record(
            request_id="request-interception",
            model="published-model",
            agent_name="Published Main Agent",
            request_raw_json='{"message":"interception"}',
            model_request_raw_json='{"messages":[]}',
        )
        client.app.state.security_events.emit(
            "configuration_updated",
            {"action": "updated", "entity": "test", "entity_id": "one"},
        )
        client.app.state.runtime_diagnostic_store.add(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level="error",
            request_id="request-runtime",
            model="published-model",
            agent_name="Published Main Agent",
            code="runtime_failed",
            exception_type="AgentRuntimeError",
            message="request failed",
        )
        response = client.get(
            "/api/event-feed", params=event_feed_params(page_size=100)
        )
        rejected = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call"),
        )

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["source"] for item in items} == {"interception", "system", "runtime"}
    assert all(
        set(item)
        == {
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
        for item in items
    )
    assert next(item for item in items if item["id"] == interception["id"])
    assert rejected.status_code == 422


def test_event_feed_deletes_filtered_runtime_records_across_pages(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = "delete-every-matching-log"
    with make_client(tmp_path, monkeypatch) as client:
        store = client.app.state.runtime_diagnostic_store
        for index in range(3):
            store.add(
                timestamp=(datetime.now(timezone.utc) + timedelta(seconds=index)).isoformat(),
                level="info",
                request_id=f"request-{index}",
                model="published-model",
                agent_name="Published Main Agent",
                code="",
                exception_type="",
                message=marker,
            )
        window = {
            **EVENT_FEED_TEST_WINDOW,
            "source": ["runtime"],
            "level": ["info"],
            "query": marker,
        }
        listed = client.get(
            "/api/event-feed", params={**window, "page_size": 2}
        ).json()
        deleted = client.post("/api/event-feed/delete", json=window)
        remaining = client.get(
            "/api/event-feed", params=event_feed_params(source="runtime", query=marker)
        ).json()

    assert listed["total"] == 3
    assert deleted.json() == {"deleted": 3}
    assert remaining["items"] == []


def test_event_feed_downloads_long_public_records_and_retention_is_scoped(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        interception = client.app.state.api_server_store.add_interception_record(
            request_id="long-interception",
            model="published-model",
            agent_name="Published Main Agent",
            request_raw_json='{"message":"' + "拦" * 5000 + '"}',
            model_request_raw_json='{"messages":[]}',
        )
        listing = client.get(
            "/api/event-feed",
            params=event_feed_params(source="interception", page_size=100),
        ).json()
        item = next(row for row in listing["items"] if row["id"] == interception["id"])
        download = client.get(f"/api/event-feed/interception/{item['id']}/download")
        retention = client.put(
            "/api/interception-test/records/retention", json={"retention_limit": 10_000}
        )
        runtime_retention = client.put(
            "/api/runtime-diagnostics/retention", json={"retention_limit": 10_000}
        )
        obsolete = client.put(
            "/api/api-server/history/retention", json={"retention_limit": 10}
        )

    assert item["inline_content"] is None
    assert item["download_available"] is True
    assert download.status_code == 200
    assert json.loads(download.content.decode("utf-8"))["source"] == "interception"
    assert retention.json()["retention_limit"] == 10_000
    assert runtime_retention.json()["retention_limit"] == 10_000
    assert obsolete.status_code == 404
