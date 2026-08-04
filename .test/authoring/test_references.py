from __future__ import annotations

from .reference_support import *


def test_default_deep_agent_tool_conflict_is_rejected_at_save(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "read_file", "read_file")
    blocks = create_blocks(
        client,
        "default-tool-conflict",
        ("model", "output-mode", "custom-tool"),
    )
    selected = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["read_file"]},
    )
    assert selected.status_code == 200, selected.text

    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Default tool conflict",
            "capability_refs": references(
                blocks,
                ("model", "output-mode", "custom-tool"),
            ),
        },
    )

    assert primary.status_code == 422
    issues = primary.json()["detail"]["validation"]["issues"]
    assert any(
        issue["code"] == "assembly.tool_name_conflict"
        and issue["path"] == "tools.read_file"
        for issue in issues
    )


def test_minimal_filesystem_allows_non_read_file_tool_names(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "workspace_list", "ls")
    blocks = create_blocks(
        client,
        "minimal-filesystem",
        ("model", "output-mode", "custom-tool"),
    )
    selected = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["workspace_list"]},
    )
    assert selected.status_code == 200, selected.text

    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Minimal filesystem",
            "capability_refs": references(
                blocks,
                ("model", "output-mode", "custom-tool"),
            ),
        },
    )

    assert primary.status_code == 200, primary.text


def test_block_update_rejects_new_conflict_in_referencing_primary(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "safe_tool", "safe_tool")
    write_custom_tool(tmp_path, "write_todos", "write_todos")
    blocks = create_blocks(
        client,
        "impact",
        ("model", "filesystem", "output-mode", "todo-list", "custom-tool"),
    )
    safe = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["safe_tool"]},
    )
    assert safe.status_code == 200, safe.text
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Protected Primary",
            "capability_refs": references(
                blocks,
                ("model", "filesystem", "output-mode", "todo-list", "custom-tool"),
            ),
        },
    )
    assert primary.status_code == 200, primary.text

    rejected = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["write_todos"]},
    )

    assert rejected.status_code == 422
    issues = rejected.json()["detail"]["validation"]["issues"]
    assert any(issue["code"] == "assembly.tool_name_conflict" for issue in issues)
    stored = client.get(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}"
    ).json()
    assert stored["tools"] == ["safe_tool"]

def test_static_tool_conflicts_use_ast_declared_name_not_resource_filename(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "write_todos", "renamed_runtime_tool")
    blocks = create_blocks(
        client,
        "declared-tool-name",
        ("model", "filesystem", "output-mode", "todo-list", "custom-tool"),
    )
    selected = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["write_todos"]},
    )
    assert selected.status_code == 200, selected.text

    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "No false tool conflict",
            "capability_refs": references(
                blocks,
                ("model", "filesystem", "output-mode", "todo-list", "custom-tool"),
            ),
        },
    )

    assert primary.status_code == 200, primary.text

def test_hidden_delete_only_conflicts_after_filesystem_enables_it(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "delete", "delete")
    blocks = create_blocks(
        client,
        "delete-opt-in",
        ("model", "filesystem", "output-mode", "custom-tool"),
    )
    selected = client.put(
        f"/api/blocks/custom-tool/{blocks['custom-tool']['id']}",
        json={"name": blocks["custom-tool"]["name"], "tools": ["delete"]},
    )
    assert selected.status_code == 200, selected.text
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Delete opt-in Primary",
            "capability_refs": references(
                blocks,
                ("model", "filesystem", "output-mode", "custom-tool"),
            ),
        },
    )
    assert primary.status_code == 200, primary.text

    enabled = client.put(
        f"/api/blocks/filesystem/{blocks['filesystem']['id']}",
        json={
            "name": blocks["filesystem"]["name"],
            "tool_configs": {"delete": {"visible": True}},
        },
    )

    assert enabled.status_code == 422
    issues = enabled.json()["detail"]["validation"]["issues"]
    assert any(
        issue["code"] == "assembly.tool_name_conflict"
        and issue["path"] == "tools.delete"
        for issue in issues
    )

def test_override_update_rejects_new_conflict_in_bound_subagent(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    write_custom_tool(tmp_path, "safe_tool", "safe_tool")
    write_custom_tool(tmp_path, "write_todos", "write_todos")
    blocks = create_blocks(
        client,
        "override-impact",
        ("model", "filesystem", "output-mode", "todo-list", "subagent"),
    )
    delegation = client.put(
        f"/api/blocks/subagent/{blocks['subagent']['id']}",
        json={"name": blocks["subagent"]["name"]},
    )
    assert delegation.status_code == 200, delegation.text
    safe_tool = client.post(
        "/api/blocks/custom-tool",
        json={"name": "Safe child tools", "tools": ["safe_tool"]},
    ).json()
    conflict_tool = client.post(
        "/api/blocks/custom-tool",
        json={"name": "Conflicting child tools", "tools": ["write_todos"]},
    ).json()
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Bound Subagent",
            name="worker",
            description="Handle delegated work.",
            capability_overrides=[
                {"type": "custom-tool", "mode": "replace", "block_id": safe_tool["id"]}
            ],
        ),
    )
    assert subagent.status_code == 200, subagent.text
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Delegating Primary",
            "capability_refs": references(
                blocks,
                ("model", "filesystem", "output-mode", "todo-list", "subagent"),
            ),
            "subagents": [{"subagent_id": subagent.json()["id"]}],
        },
    )
    assert primary.status_code == 200, primary.text

    rejected = client.put(
        f"/api/subagents/{subagent.json()['id']}",
        json=subagent_payload(
            "Bound Subagent",
            name="worker",
            description="Handle delegated work.",
            capability_overrides=[
                {
                    "type": "custom-tool",
                    "mode": "replace",
                    "block_id": conflict_tool["id"],
                }
            ],
        ),
    )

    assert rejected.status_code == 422
    issues = rejected.json()["detail"]["validation"]["issues"]
    assert any(issue["code"] == "assembly.tool_name_conflict" for issue in issues)
    stored = client.get(f"/api/subagents/{subagent.json()['id']}").json()
    assert stored["settings"]["capability_overrides"][0]["block_id"] == safe_tool["id"]
def test_repository_report_owns_invalid_subagent_issue_by_primary(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    blocks = create_blocks(client, "subagent-owner")
    delegation = client.post(
        "/api/blocks/subagent",
        json={"name": "Delegation owner"},
    ).json()
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Subagent owner Primary",
            "capability_refs": [
                *references(blocks, ("model", "filesystem", "output-mode")),
                {"type": "subagent", "block_id": delegation["id"]},
            ],
            "subagents": [{
                "subagent_id": "00000000-0000-0000-0000-000000000000"
            }],
        },
    )
    assert primary.status_code == 422

    valid_primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Subagent owner Primary",
            "capability_refs": references(
                blocks, ("model", "filesystem", "output-mode")
            ),
            "subagents": [],
        },
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM primary_agents WHERE id = ?", (valid_primary["id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["capability_refs"].append(
            {"type": "subagent", "block_id": delegation["id"]}
        )
        payload["subagents"] = [{
            "subagent_id": "00000000-0000-0000-0000-000000000000"
        }]
        connection.execute(
            "UPDATE primary_agents SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), valid_primary["id"]),
        )

    issues = client.get("/api/validation/repository").json()["issues"]
    issue = next(
        item
        for item in issues
        if item["code"] == "assembly.subagent_not_found"
    )
    assert issue["scope"] == "subagent"
    assert issue["owner_id"] == valid_primary["id"]
    assert issue["owner_name"] == "Subagent owner Primary"
def test_generic_draft_validation_covers_each_target_without_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    block_report = client.post(
        "/api/validation/draft",
        json={
            "target": {"kind": "block", "type": "system-prompt"},
            "payload": {
                "name": "Draft prompt",
                "system_prompt": "Text",
                "legacy_field": True,
            },
        },
    )
    primary_report = client.post(
        "/api/validation/draft",
        json={
            "target": {"kind": "primary"},
            "payload": {"name": "Draft Primary", "capability_refs": []},
        },
    )
    subagent_report = client.post(
        "/api/validation/draft",
        json={
            "target": {"kind": "subagent"},
            "payload": subagent_payload(
                "Draft Subagent",
                name="draft_worker",
                capability_overrides=[
                    {
                        "type": "model",
                        "mode": "replace",
                        "block_id": "00000000-0000-0000-0000-000000000000",
                    }
                ],
            ),
        },
    )

    assert block_report.status_code == 200
    assert primary_report.status_code == 200
    assert subagent_report.status_code == 200
    assert block_report.json()["issues"][0]["code"] == "contract.unknown_field"
    assert any(
        issue["code"] == "assembly.required_capability_missing"
        for issue in primary_report.json()["issues"]
    )
    assert subagent_report.json()["issues"][0]["code"] == "assembly.reference_not_found"
    assert client.get("/api/blocks/system-prompt").json() == []
    assert client.get("/api/primary-agents").json() == []
    assert client.get("/api/subagents").json() == []


def test_draft_validation_rejects_unknown_block_type_with_localized_detail(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/validation/draft",
        json={
            "target": {"kind": "block", "type": "unknown-block"},
            "payload": {},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "unknown_configuration_type",
        "message": "The requested configuration type is not supported.",
        "message_key": "errors.unknownConfigurationType",
        "message_args": {"type": "unknown-block"},
    }
