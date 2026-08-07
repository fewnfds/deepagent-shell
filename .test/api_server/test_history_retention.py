from __future__ import annotations

from .support import *


def retention_settings(value: int) -> dict[str, int]:
    return {"retention_limit": value, "max_retention_limit": 10_000}

def test_history_page_retention_limits_trim_oldest_records_and_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_paths = (
        "/api/api-server/history/retention",
        "/api/agent-sessions/retention",
        "/api/interception-test/records/retention",
    )

    def send_three(client: TestClient, main_agent: dict, prefix: str) -> None:
        for index in range(3):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": main_agent["name"],
                    "messages": [{"role": "user", "content": f"{prefix}-{index}"}],
                },
            )
            assert response.status_code == 200, response.text

    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        for path in settings_paths:
            assert client.get(path).json() == retention_settings(20)
        send_three(client, main_agent, "retention")

        assert client.put(
            "/api/api-server/history/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        assert len(client.get(
            "/api/event-feed", params=event_feed_params(source="api_call", page_size=100)
        ).json()["items"]) == 2

        assert client.put(
            "/api/agent-sessions/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        sessions = client.get("/api/agent-sessions").json()
        assert sessions["total"] == 2

        client.put("/api/interception-test", json={"enabled": True})
        send_three(client, main_agent, "capture")
        assert client.put(
            "/api/interception-test/records/retention",
            json={"retention_limit": 2},
        ).json() == retention_settings(2)
        assert len(client.get(
            "/api/event-feed", params=event_feed_params(source="interception", page_size=100)
        ).json()["items"]) == 2

        diagnostics = client.app.state.runtime_diagnostics
        assert client.put(
            "/api/runtime-diagnostics/retention",
            json={"retention_limit": 2},
        ).json()["retention_limit"] == 2
        for index in range(3):
            diagnostics.request_started(
                request_id=f"runtime-{index}", model="model", agent_name="agent"
            )
        runtime = client.get(
            "/api/event-feed", params=event_feed_params(source="runtime", page_size=100)
        ).json()
        assert {item["request_id"] for item in runtime["items"]} == {
            "runtime-1",
            "runtime-2",
        }

    with make_client(tmp_path, monkeypatch) as restarted:
        for path in settings_paths:
            assert restarted.get(path).json() == retention_settings(2)
        assert restarted.get("/api/runtime-diagnostics").json()["retention_limit"] == 2

def test_agent_session_retention_keeps_or_deletes_every_run_as_one_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(client: TestClient, main_agent: dict, session_id: str, message: str) -> None:
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Agent-Session-ID": session_id},
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": message}],
            },
        )
        assert response.status_code == 200, response.text

    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        run(client, main_agent, "session-old", "old first")
        run(client, main_agent, "session-old", "old second")
        run(client, main_agent, "session-middle", "middle first")
        run(client, main_agent, "session-middle", "middle second")
        run(client, main_agent, "session-new", "new only")

        updated = client.put(
            "/api/agent-sessions/retention",
            json={"retention_limit": 2},
        )
        listing = client.get("/api/agent-sessions").json()
        old = client.get("/api/agent-sessions/session-old")
        middle = client.get("/api/agent-sessions/session-middle").json()
        new = client.get("/api/agent-sessions/session-new").json()

    assert updated.json() == retention_settings(2)
    assert listing["total"] == 2
    assert {item["session_id"] for item in listing["items"]} == {
        "session-middle",
        "session-new",
    }
    assert old.status_code == 404
    assert [
        run_item["input_messages"][0]["content"] for run_item in middle["runs"]
    ] == ["middle first", "middle second"]
    assert len(new["runs"]) == 1
