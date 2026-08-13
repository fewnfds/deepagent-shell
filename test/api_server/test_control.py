from __future__ import annotations

from .support import *

def test_api_key_is_write_only_and_takes_effect_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "page-inference-key"
    with make_client(tmp_path, monkeypatch) as client:
        initial = client.get("/v1/models")
        saved = client.put(
            "/api/api-server",
            json={"api_key": {"operation": "replace", "value": secret}},
        )
        missing = client.get("/v1/models", headers={"Authorization": ""})
        wrong = client.get(
            "/v1/models", headers={"Authorization": "Bearer wrong-key"}
        )
        allowed = client.get(
            "/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )
        status = client.get("/api/api-server")

    with ScopedAuthTestClient(create_app()) as restarted:
        persisted = restarted.get(
            "/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )

    assert initial.status_code == 200
    assert saved.status_code == 200
    assert saved.json()["api_key"] == {"configured": True}
    assert secret not in saved.text
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
    assert persisted.status_code == 200
    assert secret not in status.text

def test_start_stop_and_known_workflow_runs_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        workflow = create_workflow(client, name="Runnable later")
        stopped = client.post("/api/api-server/stop")
        unavailable = client.get("/v1/models")
        started = client.post("/api/api-server/start")
        models = client.get("/v1/models")
        completion = client.post(
            "/v1/chat/completions",
            json={
                "model": workflow["name"],
                "messages": [{"role": "user", "content": "stream"}],
                "stream": False,
            },
        )

    assert stopped.json()["enabled"] is False
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "api_server_stopped"
    assert started.json()["enabled"] is True
    assert [item["id"] for item in models.json()["data"]] == [workflow["name"]]
    assert completion.status_code == 422
    assert completion.json()["error"]["code"] == "workflow.start_required"
