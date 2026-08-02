from __future__ import annotations

from .support import *


def test_subagent_binding_semantics_return_all_field_level_issues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        payload = {
            "name": primary["name"],
            "capability_refs": primary["capability_refs"],
            "subagents": [
                {
                    "name": "",
                    "description": "Has a description.",
                    "subagent_override_id": "",
                },
                {
                    "name": "中文名称",
                    "description": "Has a description.",
                    "subagent_override_id": "",
                },
                {
                    "name": "worker",
                    "description": "",
                    "subagent_override_id": "",
                },
                {
                    "name": "worker",
                    "description": "Duplicate name.",
                    "subagent_override_id": "",
                },
            ],
        }

        draft = client.post(
            "/api/validation/draft",
            json={"target": {"kind": "primary"}, "payload": payload},
        )
        saved = client.put(
            f"/api/primary-agents/{primary['id']}",
            json=payload,
        )

    expected = {
        (
            "contract.subagent_name_required",
            "subagents[0].name",
        ),
        (
            "contract.subagent_name_format_invalid",
            "subagents[1].name",
        ),
        (
            "contract.subagent_description_required",
            "subagents[2].description",
        ),
        (
            "contract.subagent_name_duplicate",
            "subagents[3].name",
        ),
    }
    assert draft.status_code == 200
    draft_issues = draft.json()["issues"]
    assert {(issue["code"], issue["path"]) for issue in draft_issues} == expected
    assert saved.status_code == 422
    saved_issues = saved.json()["detail"]["validation"]["issues"]
    assert {(issue["code"], issue["path"]) for issue in saved_issues} == expected
    assert all(issue["scope"] == "primary" for issue in saved_issues)
    assert not any(
        issue["code"] == "contract.invalid_value" and not issue["path"]
        for issue in saved_issues
    )


def test_removed_subagent_binding_enabled_field_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        primary = create_primary(client)
        response = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": primary["capability_refs"],
                "subagents": [
                    {
                        "enabled": False,
                        "name": "中文草稿",
                        "description": "",
                        "subagent_override_id": "",
                    }
                ],
            },
        )

    assert response.status_code == 422
    issues = response.json()["detail"]["validation"]["issues"]
    assert any(
        issue["code"] == "contract.unknown_field"
        and issue["path"] == "subagents[0].enabled"
        for issue in issues
    )
