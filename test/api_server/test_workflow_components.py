from __future__ import annotations

from .support import *


def definition_payload(name: str = "Approval router") -> dict[str, object]:
    return {
        "name": name,
        "description": "Routes a request using reusable Python logic.",
        "runtime_kind": "python-command",
        "state_contract": "agent-shell.workflow.agent-invocations.v1",
        "input_endpoints": [
            {
                "id": "in",
                "label": "Input",
                "activation": "any",
                "accepted_edge_types": ["normal", "conditional"],
                "max_connections": None,
            }
        ],
        "output_endpoints": [
            {
                "id": "approved",
                "label": "Approved",
                "edge_type": "conditional",
                "max_connections": 1,
            },
            {
                "id": "rejected",
                "label": "Rejected",
                "edge_type": "conditional",
                "max_connections": 1,
            },
        ],
        "config_schema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "integer", "minimum": 1},
            },
            "required": ["threshold"],
            "additionalProperties": False,
        },
        "python_source": (
            "async def run(input):\n"
            "    route = 'approved' if input['config']['threshold'] > 1 else 'rejected'\n"
            "    return {'update': {}, 'route': route}\n"
        ),
        "python_requirements": ["pydantic>=2", "httpx>=0.28"],
    }


def test_workflow_component_definition_and_instance_crud_reload_from_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        definition_response = client.post(
            "/api/workflow-component-definitions",
            json=definition_payload(),
        )
        assert definition_response.status_code == 200, definition_response.text
        definition = definition_response.json()
        assert definition["python_requirements"] == ["httpx>=0.28", "pydantic>=2"]
        assert definition["requirements_fingerprint"]

        instance_response = client.post(
            "/api/workflow-component-instances",
            json={
                "definition_id": definition["id"],
                "name": "High risk approval",
                "description": "A materialized router configuration.",
                "config": {"threshold": 3},
            },
        )
        assert instance_response.status_code == 200, instance_response.text
        instance = instance_response.json()
        assert client.get(
            "/api/workflow-component-instances",
            params={"definition_id": definition["id"]},
        ).json() == [instance]

        updated = client.put(
            f"/api/workflow-component-instances/{instance['id']}",
            json={
                "definition_id": definition["id"],
                "name": "High risk approval",
                "description": "Updated instance.",
                "config": {"threshold": 5},
            },
        )
        assert updated.status_code == 200, updated.text
        instance = updated.json()

    definition_path = (
        tmp_path
        / "data"
        / "config"
        / "workflow-components"
        / "definitions"
        / f"{definition['id']}.yaml"
    )
    instance_path = (
        tmp_path
        / "data"
        / "config"
        / "workflow-components"
        / "instances"
        / f"{instance['id']}.yaml"
    )
    assert definition_path.is_file()
    assert instance_path.is_file()

    with make_client(tmp_path, monkeypatch) as client:
        assert client.get(
            f"/api/workflow-component-definitions/{definition['id']}"
        ).json()["name"] == definition["name"]
        assert client.get(
            f"/api/workflow-component-instances/{instance['id']}"
        ).json() == instance

        protected = client.delete(
            f"/api/workflow-component-definitions/{definition['id']}"
        )
        assert protected.status_code == 409
        assert protected.json()["detail"]["code"] == (
            "workflow_component_definition_referenced"
        )

        assert client.delete(
            f"/api/workflow-component-instances/{instance['id']}"
        ).json() == {"ok": True}
        assert client.delete(
            f"/api/workflow-component-definitions/{definition['id']}"
        ).json() == {"ok": True}

    assert not definition_path.exists()
    assert not instance_path.exists()


def test_workflow_component_schema_and_instance_config_are_authoritative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        invalid_definition = definition_payload("Invalid schema")
        invalid_definition["config_schema"] = {"type": "array"}
        rejected_definition = client.post(
            "/api/workflow-component-definitions",
            json=invalid_definition,
        )
        assert rejected_definition.status_code == 422
        assert rejected_definition.json()["detail"]["code"] == (
            "workflow_component_definition_invalid"
        )

        definition = client.post(
            "/api/workflow-component-definitions",
            json=definition_payload(),
        ).json()
        rejected_instance = client.post(
            "/api/workflow-component-instances",
            json={
                "definition_id": definition["id"],
                "name": "Invalid config",
                "description": "Missing threshold.",
                "config": {},
            },
        )
        assert rejected_instance.status_code == 422
        assert rejected_instance.json()["detail"]["code"] == (
            "workflow_component_instance_config_invalid"
        )

        instance = client.post(
            "/api/workflow-component-instances",
            json={
                "definition_id": definition["id"],
                "name": "Valid config",
                "description": "Uses the current schema.",
                "config": {"threshold": 2},
            },
        ).json()
        changed_definition = definition_payload()
        changed_definition["config_schema"] = {
            "type": "object",
            "properties": {"mode": {"type": "string"}},
            "required": ["mode"],
            "additionalProperties": False,
        }
        rejected_update = client.put(
            f"/api/workflow-component-definitions/{definition['id']}",
            json=changed_definition,
        )
        assert rejected_update.status_code == 409
        assert rejected_update.json()["detail"]["code"] == (
            "workflow_component_definition_instances_invalid"
        )
        assert client.get(
            f"/api/workflow-component-instances/{instance['id']}"
        ).json()["config"] == {"threshold": 2}
