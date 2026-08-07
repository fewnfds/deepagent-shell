from __future__ import annotations

from pathlib import Path

from .app_support import make_client


def workflow_payload(public_id: str = "workflow-echo") -> dict[str, object]:
    return {
        "public_id": public_id,
        "name": "Echo workflow",
        "description": "A deterministic workflow used by authoring tests.",
        "root_interface": {"kind": "chat", "input": "messages", "output": "message"},
        "nodes": [
            {"id": "input", "type": "builtin.input.messages", "version": "1.0.0", "config": {}},
            {"id": "output", "type": "builtin.output.message", "version": "1.0.0", "config": {}},
        ],
        "edges": [
            {
                "id": "input-output",
                "source": {"node": "input", "port": "messages"},
                "target": {"node": "output", "port": "messages"},
            }
        ],
    }


def test_workflow_crud_and_revision_conflict(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/workflows", json=workflow_payload())
    assert created.status_code == 200, created.text
    item = created.json()
    assert item["public_id"] == "workflow-echo"
    assert item["revision"] == 1

    updated_payload = workflow_payload()
    updated_payload["description"] = "updated"
    updated = client.put(
        f"/api/workflows/{item['id']}",
        json={**updated_payload, "revision": item["revision"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2

    conflict = client.put(
        f"/api/workflows/{item['id']}",
        json={**updated_payload, "revision": 1},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "workflow_revision_conflict"


def test_workflow_validator_rejects_cycle_and_bad_port(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = workflow_payload()
    payload["edges"] = [
        {
            "id": "input-output",
            "source": {"node": "input", "port": "missing"},
            "target": {"node": "output", "port": "messages"},
        },
        {
            "id": "output-input",
            "source": {"node": "output", "port": "messages"},
            "target": {"node": "input", "port": "messages"},
        },
    ]
    response = client.post("/api/workflows", json=payload)
    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["detail"]["validation"]["issues"]}
    assert "workflow.source_port_missing" in codes
