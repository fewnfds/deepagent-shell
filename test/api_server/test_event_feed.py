from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agent_shell.runtime.errors import AgentRuntimeError

from .support import *


def test_event_feed_exposes_only_supported_sources(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
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
    assert {item["source"] for item in items} == {"system", "runtime"}
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


def test_runtime_debug_download_keeps_full_exception_out_of_summary(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_id = "request-full-debug"
    private_detail = "private-debug-detail"
    with make_client(tmp_path, monkeypatch) as client:
        initial = client.get("/api/runtime-diagnostics")
        enabled = client.put(
            "/api/runtime-diagnostics/debug",
            json={"enabled": True},
        )

        try:
            try:
                raise TypeError(private_detail)
            except TypeError as cause:
                raise RuntimeError("outer debug failure") from cause
        except RuntimeError as full_exception:
            client.app.state.runtime_diagnostics.runtime_error(
                AgentRuntimeError(
                    "agent_execution_failed",
                    "The Agent failed during graph execution.",
                    status_code=502,
                ),
                request_id=request_id,
                model="published-model",
                agent_name="Published Main Agent",
                code="agent_execution_failed",
                debug_exception=full_exception,
            )

        listing = client.get(
            "/api/event-feed",
            params=event_feed_params(source="runtime", query=request_id),
        ).json()
        item = listing["items"][0]
        download = client.get(
            f"/api/event-feed/runtime/{item['id']}/download"
        )
        deleted = client.post(
            "/api/event-feed/delete",
            json={
                **EVENT_FEED_TEST_WINDOW,
                "source": ["runtime"],
                "level": [],
                "query": request_id,
            },
        )
        missing = client.get(
            f"/api/event-feed/runtime/{item['id']}/download"
        )

    assert initial.json()["debug_enabled"] is False
    assert enabled.json()["debug_enabled"] is True
    assert item["download_available"] is True
    assert private_detail not in item["inline_content"]
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/plain")
    assert download.headers["content-disposition"].endswith('.log"')
    debug_text = download.content.decode("utf-8")
    assert "TypeError: private-debug-detail" in debug_text
    assert "RuntimeError: outer debug failure" in debug_text
    assert deleted.json() == {"deleted": 1}
    assert missing.status_code == 404
    assert list((tmp_path / "data" / "logs" / "debug").glob("*.log")) == []
