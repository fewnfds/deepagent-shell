from __future__ import annotations

from .app_support import *


def create_block(client, block_type: str, payload: dict) -> dict:
    response = client.post(f"/api/blocks/{block_type}", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_worker_profile_and_binding_resolve_separate_prompt_presets(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    model = create_block(client, "model", model_payload("Shared model"))
    output = create_block(client, "output-mode", output_mode_payload("Output"))
    delegation = create_block(
        client,
        "worker-delegation",
        {"name": "Worker delegation", "max_worker_calls_per_request": 4},
    )
    primary_preset = create_block(
        client,
        "prompt-preset",
        {
            "name": "Primary startup",
            "startup_messages": [
                {
                    "role": "user",
                    "content_template": "Available workers:\n{available_workers}",
                }
            ],
        },
    )
    worker_preset = create_block(
        client,
        "prompt-preset",
        {
            "name": "Worker startup",
            "startup_messages": [
                {"role": "user", "content_template": "Task: {task}"},
                {"role": "assistant", "content_template": "Understood."},
                {"role": "user", "content_template": "Begin."},
            ],
        },
    )

    profile_response = client.post(
        "/api/worker-profiles",
        json={
            "name": "Task worker",
            "include_client_messages": True,
            "capability_overrides": [
                {
                    "type": "prompt-preset",
                    "mode": "replace",
                    "block_id": worker_preset["id"],
                }
            ],
        },
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()

    primary_response = client.post(
        "/api/primary-agents",
        json={
            "name": "Coordinator",
            "capability_refs": [
                {"type": "model", "block_id": model["id"]},
                {"type": "output-mode", "block_id": output["id"]},
                {"type": "prompt-preset", "block_id": primary_preset["id"]},
                {"type": "worker-delegation", "block_id": delegation["id"]},
            ],
            "workers": [
                {
                    "name": "reviewer",
                    "description": "Review the assigned material.",
                    "worker_profile_id": profile["id"],
                }
            ],
        },
    )
    assert primary_response.status_code == 200, primary_response.text
    primary = primary_response.json()
    assert primary["workers"][0]["worker_profile_id"] == profile["id"]

    referenced = client.delete(f"/api/worker-profiles/{profile['id']}")
    assert referenced.status_code == 409


def test_worker_profile_rejects_primary_only_capability(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    output = create_block(client, "output-mode", output_mode_payload("Output"))
    response = client.post(
        "/api/worker-profiles",
        json={
            "name": "Invalid worker",
            "capability_overrides": [
                {
                    "type": "output-mode",
                    "mode": "replace",
                    "block_id": output["id"],
                }
            ],
        },
    )
    assert response.status_code == 422
