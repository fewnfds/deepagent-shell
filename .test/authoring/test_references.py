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

def test_block_copy_revalidates_stored_payload_before_writing(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    block = client.post(
        "/api/blocks/system-prompt",
        json={"name": "Old prompt", "system_prompt": "Keep this text."},
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM blocks WHERE id = ?", (block["id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["legacy_field"] = True
        connection.execute(
            "UPDATE blocks SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), block["id"]),
        )

    rejected = client.post(
        f"/api/blocks/system-prompt/{block['id']}/copy",
        json={"name": "Rejected copy"},
    )

    assert rejected.status_code == 422
    issues = rejected.json()["detail"]["validation"]["issues"]
    assert any(issue["code"] == "contract.unknown_field" for issue in issues)
    names = [item["name"] for item in client.get("/api/blocks/system-prompt").json()]
    assert "Rejected copy" not in names

def test_repository_validation_reports_raw_historical_fields_without_rewriting(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    blocks = create_blocks(client, "repository")
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Repository Primary",
            "capability_refs": references(
                blocks, ("model", "filesystem", "output-mode")
            ),
        },
    )
    assert primary.status_code == 200, primary.text
    healthy = client.get("/api/validation/repository")
    assert healthy.status_code == 200
    assert healthy.json() == {
        "valid": True,
        "stage": "repository_load",
        "issues": [],
    }

    prompt = blocks["system-prompt"]
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM blocks WHERE id = ?", (prompt["id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["legacy_field"] = r"C:\private\legacy.json"
        connection.execute(
            "UPDATE blocks SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), prompt["id"]),
        )

    report = client.get("/api/validation/repository")

    assert report.status_code == 200
    issue = next(
        item
        for item in report.json()["issues"]
        if item["owner_id"] == prompt["id"] and item["path"] == "legacy_field"
    )
    assert issue["code"] == "contract.unknown_field"
    assert "private" not in issue["message"]
    raw = client.get(f"/api/blocks/system-prompt/{prompt['id']}").json()
    assert raw["legacy_field"] == r"C:\private\legacy.json"

def test_repository_validation_reports_unknown_stored_block_type(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    required = create_blocks(
        client,
        "unknown-type-owner",
        ("model", "output-mode"),
    )
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Historical Primary",
            "capability_refs": references(required, ("model", "output-mode")),
        },
    ).json()
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload("Historical Subagent", name="historical_worker"),
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    block_id = "00000000-0000-0000-0000-000000000014"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "INSERT INTO blocks (id, block_type, name, payload) VALUES (?, ?, ?, ?)",
            (block_id, "removed-capability", "Historical component", "{}"),
        )
        primary_payload = json.loads(
            connection.execute(
                "SELECT payload FROM primary_agents WHERE id = ?",
                (primary["id"],),
            ).fetchone()[0]
        )
        primary_payload["capability_refs"].append(
            {"type": "removed-capability", "block_id": block_id}
        )
        connection.execute(
            "UPDATE primary_agents SET payload = ? WHERE id = ?",
            (json.dumps(primary_payload, ensure_ascii=False), primary["id"]),
        )
        subagent_payload_json = json.loads(
            connection.execute(
                "SELECT payload FROM subagents WHERE id = ?",
                (subagent["id"],),
            ).fetchone()[0]
        )
        subagent_payload_json["settings"]["capability_overrides"].append(
            {
                "type": "removed-capability",
                "mode": "replace",
                "block_id": block_id,
            }
        )
        connection.execute(
            "UPDATE subagents SET payload = ? WHERE id = ?",
            (json.dumps(subagent_payload_json, ensure_ascii=False), subagent["id"]),
        )

    report = client.get("/api/validation/repository")

    assert report.status_code == 200
    assert any(
        issue["code"] == "storage.unknown_block_type"
        and issue["owner_id"] == block_id
        and issue["owner_type"] == "removed-capability"
        for issue in report.json()["issues"]
    )

    deleted = client.delete(f"/api/unsupported-blocks/{block_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    stored_primary = client.get(f"/api/primary-agents/{primary['id']}").json()
    stored_subagent = client.get(f"/api/subagents/{subagent['id']}").json()
    assert all(
        item["type"] != "removed-capability"
        for item in stored_primary["capability_refs"]
    )
    assert all(
        item["type"] != "removed-capability"
        for item in stored_subagent["settings"]["capability_overrides"]
    )
    assert client.get("/api/validation/repository").json() == {
        "valid": True,
        "stage": "repository_load",
        "issues": [],
    }


def test_unsupported_block_delete_rejects_current_component_types(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    block = client.post(
        "/api/blocks/system-prompt",
        json={"name": "Current prompt", "system_prompt": "Follow the request."},
    ).json()

    response = client.delete(f"/api/unsupported-blocks/{block['id']}")

    assert response.status_code == 404
    assert client.get(f"/api/blocks/system-prompt/{block['id']}").status_code == 200

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

def test_invalid_historical_primary_does_not_break_unrelated_delete_paths(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    blocks = create_blocks(
        client,
        "invalid-delete-owner",
        ("model", "filesystem", "output-mode", "system-prompt"),
    )
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Historical invalid delete owner",
            "capability_refs": references(
                blocks, ("model", "filesystem", "output-mode")
            ),
            "subagents": [],
        },
    ).json()
    subagent = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Unrelated deletable Subagent",
            name="unrelated_worker",
        ),
    ).json()
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT payload FROM primary_agents WHERE id = ?", (primary["id"],)
        ).fetchone()
        payload = json.loads(row[0])
        payload["capability_refs"] = None
        payload["subagents"] = {"legacy": True}
        connection.execute(
            "UPDATE primary_agents SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), primary["id"]),
        )

    report = client.get("/api/validation/repository")
    deleted_block = client.delete(
        f"/api/blocks/system-prompt/{blocks['system-prompt']['id']}"
    )
    deleted_subagent = client.delete(f"/api/subagents/{subagent['id']}")

    assert report.status_code == 200
    assert report.json()["valid"] is False
    assert deleted_block.status_code == 200, deleted_block.text
    assert deleted_subagent.status_code == 200, deleted_subagent.text

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
