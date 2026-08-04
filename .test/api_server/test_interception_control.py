from __future__ import annotations

from .support import *

def test_interception_records_are_persistent_paged_searchable_and_deletable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    RecordingFakeListChatModel.seen_messages = []
    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: RecordingFakeListChatModel(
                responses=["provider must not run"]
            ),
        )
        primary = create_primary(client)
        enabled = client.put("/api/interception-test", json={"enabled": True})
        assert enabled.json() == {"enabled": True}
        for number in range(3):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": primary["name"],
                    "messages": [{"role": "user", "content": f"message-{number}"}],
                    "metadata": {"number": number},
                },
            )
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == INTERCEPTION_REPLY

        first_page = client.get(
            "/api/event-feed",
            params=event_feed_params(source="interception", page_size=2),
        ).json()
        searched = client.get(
            "/api/event-feed",
            params=event_feed_params(source="interception", query="message-1"),
        ).json()
        current = client.get(
            "/api/event-feed/interception/"
            f"{first_page['items'][0]['id']}/download"
        ).json()["entry"]
        assert len(first_page["items"]) == 2
        assert first_page["total"] == 3
        assert len(searched["items"]) == 1
        details = [
            json.loads(item["inline_content"])["entry"]
            for item in first_page["items"]
        ]
        assert all(item["name"] for item in details)
        assert all("request_raw_json" not in item for item in first_page["items"])
        assert json.loads(current["request_raw_json"])["metadata"]["number"] == 2
        assert RecordingFakeListChatModel.seen_messages == []
        assert client.get("/api/api-server/test-messages").status_code == 404

    with ScopedAuthTestClient(create_app()) as restarted:
        assert restarted.get("/api/interception-test").json() == {"enabled": True}
        persisted = restarted.get(
            "/api/event-feed", params=event_feed_params(source="interception", page_size=100)
        ).json()
        assert len(persisted["items"]) == 3
        deleted = restarted.post(
            "/api/event-feed/delete",
            json={
                **EVENT_FEED_TEST_WINDOW,
                "source": ["interception"],
                "level": [],
                "query": "",
            },
        )
        assert deleted.json() == {"deleted": 3}
        assert restarted.get(
            "/api/event-feed", params=event_feed_params(source="interception")
        ).json()["items"] == []
