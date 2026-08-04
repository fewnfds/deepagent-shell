from __future__ import annotations

from .reference_support import *


def _permission_block(client, name: str, path: str) -> dict:
    response = client.post(
        "/api/blocks/filesystem-permissions",
        json={
            "name": name,
            "permissions": [{"path": path, "permission": "read-only"}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_filesystem_path_change_reports_warning_without_rejecting_update(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    mapped = tmp_path / "mapped"
    mapped.mkdir()
    blocks = create_blocks(client, "permission-warning", ("model", "output-mode"))
    filesystem = client.post(
        "/api/blocks/filesystem",
        json={
            "name": "Shared workspace",
            "mapped_directories": [
                {"virtual_path": "/source/", "local_path": str(mapped)}
            ],
        },
    ).json()
    permissions = _permission_block(client, "Source policy", "/source/**")
    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Permission warning Primary",
            "capability_refs": [
                *references(blocks, ("model", "output-mode")),
                {"type": "filesystem", "block_id": filesystem["id"]},
                {
                    "type": "filesystem-permissions",
                    "block_id": permissions["id"],
                },
            ],
        },
    )
    assert primary.status_code == 200, primary.text
    assert client.get("/api/validation/repository").json()["issues"] == []

    updated = client.put(
        f"/api/blocks/filesystem/{filesystem['id']}",
        json={
            "name": filesystem["name"],
            "mapped_directories": [
                {"virtual_path": "/renamed/", "local_path": str(mapped)}
            ],
        },
    )

    assert updated.status_code == 200, updated.text
    report = client.get("/api/validation/repository").json()
    assert report["valid"] is True
    assert report["issues"] == [
        {
            "code": "assembly.filesystem_permission_path_unmatched",
            "scope": "primary",
            "owner_id": primary.json()["id"],
            "owner_name": "Permission warning Primary",
            "path": (
                "capability_refs.filesystem-permissions.permissions[0].path"
            ),
            "message": (
                "Permission path '/source/**' does not match a declared path "
                "in this Agent's current filesystem."
            ),
            "message_key": (
                "validation.issue.assembly.filesystemPermissionPathUnmatched"
            ),
            "message_args": {"path": "/source/**"},
            "severity": "warning",
        }
    ]


def test_subagents_inherit_replace_or_disable_filesystem_permissions(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    blocks = create_blocks(
        client,
        "permission-matrix",
        ("model", "filesystem", "output-mode", "subagent"),
    )
    parent_permissions = _permission_block(
        client, "Parent permissions", "/parent-only/**"
    )
    child_permissions = _permission_block(
        client, "Child permissions", "/child-only/**"
    )
    inherit_child = client.post(
        "/api/subagents",
        json=subagent_payload("Inherit worker", name="inherit_worker"),
    ).json()
    replace_child = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Replace worker",
            name="replace_worker",
            capability_overrides=[
                {
                    "type": "filesystem-permissions",
                    "mode": "replace",
                    "block_id": child_permissions["id"],
                }
            ],
        ),
    ).json()
    disabled_child = client.post(
        "/api/subagents",
        json=subagent_payload(
            "Disabled worker",
            name="disabled_worker",
            capability_overrides=[
                {
                    "type": "filesystem-permissions",
                    "mode": "disabled",
                    "block_id": "",
                }
            ],
        ),
    ).json()

    primary = client.post(
        "/api/primary-agents",
        json={
            "name": "Permission matrix Primary",
            "capability_refs": [
                *references(
                    blocks,
                    ("model", "filesystem", "output-mode", "subagent"),
                ),
                {
                    "type": "filesystem-permissions",
                    "block_id": parent_permissions["id"],
                },
            ],
            "subagents": [
                {"subagent_id": inherit_child["id"]},
                {"subagent_id": replace_child["id"]},
                {"subagent_id": disabled_child["id"]},
            ],
        },
    )
    assert primary.status_code == 200, primary.text

    report = client.get("/api/validation/repository").json()
    assert report["valid"] is True
    warnings = [
        issue
        for issue in report["issues"]
        if issue["code"] == "assembly.filesystem_permission_path_unmatched"
    ]
    assert {
        (issue["owner_id"], issue["message_args"]["path"])
        for issue in warnings
    } == {
        (primary.json()["id"], "/parent-only/**"),
        (inherit_child["id"], "/parent-only/**"),
        (replace_child["id"], "/child-only/**"),
    }
    assert disabled_child["id"] not in {
        issue["owner_id"] for issue in warnings
    }
    assert all(issue["severity"] == "warning" for issue in warnings)
