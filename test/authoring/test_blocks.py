from __future__ import annotations

import pytest

from .app_support import *


def test_health_catalog_and_readiness_are_small_and_current(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    assert client.get("/api/health").json() == {
        "status": "ok",
        "runtime": "model_streaming",
    }
    catalog = client.get("/api/catalog").json()
    assert set(catalog) == {
        "block_types",
        "workflow_component_types",
        "editor_defaults",
    }
    assert set(catalog["editor_defaults"]) == {
        "filesystem",
        "filesystem_permissions",
        "skill",
        "subagent",
        "todo_list",
        "output_mode",
        "exception_retry",
        "summarization",
        "prompt_caching",
        "workflow_input_context",
        "workflow_prepare",
    }
    assert [item["type"] for item in catalog["block_types"]] == list(PUBLIC_TYPES)
    assert [item["order"] for item in catalog["block_types"]] == list(range(1, 15))
    assert [item["type"] for item in catalog["workflow_component_types"]] == [
        "workflow-prepare"
    ]
    by_type = {item["type"]: item for item in catalog["block_types"]}
    assert set(by_type["model"]) == {
        "type",
        "terminology_key",
        "label",
        "order",
        "icon_key",
        "editor_key",
        "subagent_overrideable",
        "required",
        "subagent_policy",
        "tool_names",
    }
    assert by_type["model"]["required"] is True
    assert by_type["filesystem"]["required"] is False
    assert by_type["output-mode"]["required"] is True
    assert by_type["filesystem"]["tool_names"] == [
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
    ]
    assert by_type["todo-list"]["tool_names"] == ["write_todos"]
    assert by_type["output-mode"]["subagent_policy"] == "top-level-only"
    assert by_type["output-mode"]["subagent_overrideable"] is False
    readiness = client.get("/api/readiness").json()
    assert readiness["status"] == "configuration_ready"
    assert set(readiness["sections"]) == {
        "security_settings",
        "storage",
        "runtime_dependencies",
    }
    assert readiness["sections"]["storage"]["status"] == (
        "startup_permissions_confirmed"
    )
    assert readiness["sections"]["runtime_dependencies"]["status"] == "ready"
    assert readiness["sections"]["runtime_dependencies"]["code"] == "model_streaming"


def test_block_crud_round_trips_every_form_payload(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    for block_type, payload in block_cases(tmp_path):
        created_response = client.post(f"/api/blocks/{block_type}", json=payload)
        assert created_response.status_code == 200, created_response.text
        created = created_response.json()
        assert created["id"]
        assert created["name"] == payload["name"]
        if block_type == "filesystem":
            assert created["system_prompt_override"] == payload["system_prompt_override"]
            assert created["tool_token_limit_before_evict"] == 4096
            assert all(
                config["description_override"] is None
                for config in created["tool_configs"].values()
            )
        if block_type == "filesystem-permissions":
            assert created["permissions"] == payload["permissions"]
            assert created["system_prompt_override"] == payload[
                "system_prompt_override"
            ]
            assert created["tool_overrides"]["write_file"]["visible"] is False
        if block_type == "skill":
            assert created["instruction_override"] is None
        if block_type == "subagent":
            assert created["instruction_override"] is None
            assert created["task_description_override"] is None
        if block_type == "custom-middleware":
            assert created["middlewares"] == payload["middlewares"]
        if block_type == "todo-list":
            assert created["system_prompt_override"] == payload[
                "system_prompt_override"
            ]
            assert created["tool_description_override"] == payload[
                "tool_description_override"
            ]
        if block_type == "output-mode":
            assert created["event_templates"] == payload["event_templates"]

        listed = client.get(f"/api/blocks/{block_type}")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [created["id"]]
        assert client.get(f"/api/blocks/{block_type}/{created['id']}").json() == created
        update_payload = {**payload, "name": f"{payload['name']} updated"}
        if block_type == "model":
            update_payload["credential"] = None
        updated = client.put(
            f"/api/blocks/{block_type}/{created['id']}", json=update_payload
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == update_payload["name"]

        copied = client.post(
            f"/api/blocks/{block_type}/{created['id']}/copy",
            json={"name": f"{payload['name']} copy"},
        )
        assert copied.status_code == 200, copied.text
        assert copied.json()["id"] != created["id"]

        assert client.delete(f"/api/blocks/{block_type}/{created['id']}").json() == {
            "ok": True
        }
        assert client.get(f"/api/blocks/{block_type}/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "namespace",
    (
        "/large_tool_results/",
        "/conversation_history/",
        "/skills/",
        "/memory/",
        "/memories/",
    ),
)
def test_filesystem_rejects_framework_reserved_virtual_namespaces(
    tmp_path: Path, monkeypatch, namespace: str
) -> None:
    client = make_client(tmp_path, monkeypatch)
    source_dir = tmp_path / "filesystem-source"
    source_dir.mkdir()
    source_file = source_dir / "note.txt"
    source_file.write_text("ordinary user file", encoding="utf-8")
    cases = (
        (
            "mapped_directories",
            {"virtual_path": namespace, "local_path": str(source_dir)},
        ),
        (
            "virtual_directories",
            {"virtual_path": namespace, "source_path": str(source_dir)},
        ),
        (
            "virtual_files",
            {
                "virtual_path": f"{namespace}note.txt",
                "source_path": str(source_file),
            },
        ),
    )

    for index, (field, item) in enumerate(cases):
        response = client.post(
            "/api/blocks/filesystem",
            json={"name": f"Reserved namespace {index}", field: [item]},
        )
        assert response.status_code == 422, (field, namespace, response.text)
        assert namespace.rstrip("/") in response.text


def test_basic_payload_shape_errors_are_rejected(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    assert client.post("/api/blocks/model", json={"name": "only-name"}).status_code == 422
    assert (
        client.post(
            "/api/blocks/system-prompt",
            json={"name": "empty", "system_prompt": ""},
        ).status_code
        == 422
    )

    empty_skill = client.post(
        "/api/blocks/skill",
        json={"name": "Empty Skill selection", "skills": []},
    )
    removed_skill_switch = client.post(
        "/api/blocks/skill",
        json={"name": "Old Skill switch", "enabled": True, "skills": ["demo"]},
    )
    removed_subagent_switch = client.post(
        "/api/blocks/subagent",
        json={"name": "Old Subagent switch", "enabled": True},
    )

    assert empty_skill.status_code == 422, empty_skill.text
    assert removed_skill_switch.status_code == 422, removed_skill_switch.text
    assert removed_subagent_switch.status_code == 422, removed_subagent_switch.text


def test_filesystem_permissions_reject_invalid_or_duplicate_paths(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    for permissions in (
        [{"path": "relative/**", "permission": "read-only"}],
        [{"path": "/workspace/~/secret", "permission": "no-access"}],
        [
            {"path": "/workspace/**", "permission": "read-only"},
            {"path": "\\workspace\\**", "permission": "no-access"},
        ],
    ):
        response = client.post(
            "/api/blocks/filesystem-permissions",
            json={"name": "Invalid permissions", "permissions": permissions},
        )
        assert response.status_code == 422, response.text


def test_output_mode_rejects_invalid_filter_and_template_contracts(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    invalid_mapping = output_mode_payload("Invalid mapping")
    invalid_mapping["filter_mappings"] = [
        {"field": "tool_result..tool_name", "value": "commit"}
    ]

    missing_event = output_mode_payload("Missing event")
    missing_event["event_templates"].pop("lifecycle")

    extra_event = output_mode_payload("Extra event")
    extra_event["event_templates"]["raw_state"] = {
        "enabled": False,
        "template": "{{message}}",
    }

    unknown_variable = output_mode_payload("Unknown variable")
    unknown_variable["event_templates"]["assistant_text"]["template"] = (
        "{{tool_name}}"
    )

    empty_enabled_template = output_mode_payload("Empty enabled template")
    empty_enabled_template["event_templates"]["assistant_text"]["template"] = ""

    legacy_template = output_mode_payload("Legacy template")
    legacy_template["event_templates"]["assistant_text"]["start_template"] = (
        "<assistant>"
    )

    for payload in (
        invalid_mapping,
        missing_event,
        extra_event,
        unknown_variable,
        empty_enabled_template,
        legacy_template,
    ):
        response = client.post("/api/blocks/output-mode", json=payload)
        assert response.status_code == 422, (payload["name"], response.text)


def test_output_mode_reports_the_exact_malformed_event_template(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = output_mode_payload("Malformed assistant template")
    payload["event_templates"]["assistant_text"]["template"] = "{{message}"

    response = client.post("/api/blocks/output-mode", json=payload)

    assert response.status_code == 422, response.text
    issue = response.json()["detail"]["validation"]["issues"][0]
    assert issue["code"] == "contract.output_template_malformed"
    assert issue["path"] == "event_templates.assistant_text.template"
    assert issue["message_key"] == (
        "validation.issue.contract.outputTemplateMalformed"
    )
    assert issue["message_args"] == {"event_name": "assistant_text"}


def test_output_mode_accepts_a_custom_filter_field(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = output_mode_payload("Custom filter field")
    payload["filter_mappings"] = [
        {"field": "future_event.custom_field", "value": "custom value"}
    ]

    response = client.post("/api/blocks/output-mode", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["filter_mappings"] == payload["filter_mappings"]
