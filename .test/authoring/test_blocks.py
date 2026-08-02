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
    assert set(catalog) == {"block_types", "editor_defaults"}
    assert set(catalog["editor_defaults"]) == {
        "filesystem",
        "skill",
        "subagent",
            "todo_list",
            "output_mode",
            "exception_retry",
            "prompt_preset",
            "worker_delegation",
        }
    assert [item["type"] for item in catalog["block_types"]] == list(PUBLIC_TYPES)
    assert [item["order"] for item in catalog["block_types"]] == list(range(1, 13))
    by_type = {item["type"]: item for item in catalog["block_types"]}
    assert set(by_type["model"]) == {
        "type",
        "terminology_key",
        "label",
        "order",
        "icon_key",
        "editor_key",
        "subagent_overrideable",
        "worker_overrideable",
        "required",
        "subagent_policy",
        "worker_policy",
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
    assert by_type["prompt-preset"]["worker_overrideable"] is True
    assert by_type["worker-delegation"]["worker_policy"] == "guarded"
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
        if block_type == "skill":
            assert created["instruction_override"] is None
        if block_type == "subagent":
            assert created["instruction_override"] is None
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


def test_model_request_settings_accept_only_current_json_shapes(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    for index, update in enumerate(
        (
            {"tool_choice": ["auto"]},
            {"response_format": ["object"]},
            {"response_format": {"title": "Missing description"}},
            {"model_settings": ["parallel_tool_calls"]},
            {"model_settings": {"tool_choice": "required"}},
        )
    ):
        payload = {**model_payload(f"Invalid request settings {index}"), **update}
        response = client.post("/api/blocks/model", json=payload)
        assert response.status_code == 422, response.text


def test_model_request_settings_must_be_explicitly_present(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    for field in ("tool_choice", "response_format", "model_settings"):
        payload = model_payload(f"Missing {field}")
        payload.pop(field)
        response = client.post("/api/blocks/model", json=payload)

        assert response.status_code == 422, response.text
        issues = response.json()["detail"]["validation"]["issues"]
        assert any(
            issue["code"] == "contract.field_required"
            and issue["path"] == field
            for issue in issues
        )


def test_model_provider_is_required_and_limited_to_release_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    missing = model_payload("Missing Provider")
    missing.pop("provider")
    unsupported = model_payload("Unsupported Provider")
    unsupported["provider"] = "automatic"
    aliased = model_payload("Aliased Provider")
    aliased["provider"] = "google-vertexai"
    aliased["provider_settings"] = {}
    aliased["credential"] = None
    deepseek = model_payload("DeepSeek Provider")
    deepseek["provider"] = "deepseek"
    deepseek["provider_settings"] = {"max_tokens": 4096}
    openrouter = model_payload("OpenRouter Provider")
    openrouter["provider"] = "openrouter"

    assert client.post("/api/blocks/model", json=missing).status_code == 422
    assert client.post("/api/blocks/model", json=unsupported).status_code == 422
    assert client.post("/api/blocks/model", json=aliased).status_code == 422
    response = client.post("/api/blocks/model", json=deepseek)
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "deepseek"
    response = client.post("/api/blocks/model", json=openrouter)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("provider", "provider_settings", "credential"),
    [
        ("openai", {"max_completion_tokens": 512}, "secret"),
        ("anthropic", {"max_tokens_to_sample": 512, "effort": "high"}, "secret"),
        ("google_genai", {"max_tokens": 512, "retries": 2}, "secret"),
        (
            "google_vertexai",
            {"max_tokens": 512, "thinking_budget": 128},
            None,
        ),
        ("deepseek", {"max_tokens": 512, "reasoning_effort": "high"}, "secret"),
        ("xai", {"max_tokens": 512, "reasoning_effort": "high"}, "secret"),
    ],
)
def test_model_provider_settings_use_each_official_constructor_contract(
    tmp_path: Path,
    monkeypatch,
    provider: str,
    provider_settings: dict,
    credential: str | None,
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = model_payload(f"{provider} native settings")
    payload.update(
        provider=provider,
        provider_settings=provider_settings,
        credential=credential,
    )

    response = client.post("/api/blocks/model", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["provider_settings"] == provider_settings


@pytest.mark.parametrize(
    ("provider", "provider_settings", "credential"),
    [
        ("openai", {"max_tokens": 512}, "secret"),
        ("anthropic", {"max_completion_tokens": 512}, "secret"),
        ("google_genai", {"max_tokens_to_sample": 512}, "secret"),
        ("google_vertexai", {"max_tokens": 512}, "string-is-not-adc"),
    ],
)
def test_model_provider_settings_reject_cross_provider_parameters(
    tmp_path: Path,
    monkeypatch,
    provider: str,
    provider_settings: dict,
    credential: str | None,
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = model_payload(f"Invalid {provider} settings")
    payload.update(
        provider=provider,
        provider_settings=provider_settings,
        credential=credential,
    )

    response = client.post("/api/blocks/model", json=payload)

    assert response.status_code == 422

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

def test_prompt_templates_reject_unsupported_single_brace_fields(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    skill = client.post(
        "/api/blocks/skill",
        json={
            "name": "Invalid Skill prompt",
            "skills": ["demo"],
            "instruction_override": (
                'JSON {"answer": "value"}\n'
                "{skills_locations}\n{skills_load_warnings}\n{skills_list}"
            ),
        },
    )
    assert skill.status_code == 422

def test_prompt_templates_accept_escaped_literal_braces(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    skill = client.post(
        "/api/blocks/skill",
        json={
            "name": "Escaped Skill prompt",
            "skills": ["demo"],
            "instruction_override": (
                'JSON {{"answer": "value"}}\n'
                "{skills_locations}\n{skills_load_warnings}\n{skills_list}"
            ),
        },
    )
    assert skill.status_code == 200, skill.text
    assert (
        client.post(
            "/api/blocks/custom-tool",
            json={"name": "bad", "tools": ["not valid!"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "bad syntax",
                "middlewares": [
                    {"name": "broken", "source": "middleware = ("}
                ],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "missing output",
                "middlewares": [
                    {"name": "not bound", "source": "value = object()"}
                ],
            },
        ).status_code
        == 422
    )
    old_text_shape = {"enabled": True, "draft": "old shape"}
    for block_type, field in (
        ("filesystem", "system_prompt_override"),
        ("skill", "instruction_override"),
        ("subagent", "instruction_override"),
        ("todo-list", "system_prompt_override"),
    ):
        response = client.post(
            f"/api/blocks/{block_type}",
            json={"name": "old text shape", field: old_text_shape},
        )
        assert response.status_code == 422

    assert (
        client.post(
            "/api/blocks/system-prompt",
            json={"id": "client-id", "name": "bad id", "system_prompt": "x"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/primary-agents",
            json={
                "id": "client-id",
                "name": "bad id",
                "capability_refs": [],
                "subagents": [],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/subagent-overrides",
            json={
                "id": "client-id",
                "name": "bad id",
                "capability_overrides": [],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/subagent-overrides",
            json={
                "name": "explicit inherit",
                "capability_overrides": [
                    {"type": "model", "mode": "inherit", "block_id": ""}
                ],
            },
        ).status_code
        == 422
    )
    missing_credential = model_payload("Missing credential")
    del missing_credential["credential"]
    assert client.post("/api/blocks/model", json=missing_credential).status_code == 422
    assert (
        client.post(
            "/api/blocks/filesystem",
            json={"name": "bad threshold", "tool_token_limit_before_evict": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/blocks/filesystem",
            json={
                "name": "read must stay visible",
                "tool_configs": {"read_file": {"visible": False}},
            },
        ).status_code
        == 422
    )
    assert client.get("/api/blocks/not-a-type").status_code == 404

def test_model_parameters_reject_non_finite_numbers_before_storage(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/blocks/model", json=model_payload("Valid model"))
    assert created.status_code == 200, created.text

    for index, literal in enumerate(("NaN", "Infinity", "-Infinity", "1e999")):
        payload = model_payload(f"Invalid model {index}")
        raw = json.dumps(payload, separators=(",", ":")).replace(
            '"temperature":0', f'"temperature":{literal}'
        )
        response = client.post(
            "/api/blocks/model",
            content=raw,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, (literal, response.text)

    update_payload = model_payload("Invalid update")
    update_payload["credential"] = None
    raw_update = json.dumps(update_payload, separators=(",", ":")).replace(
        '"temperature":0', '"temperature":NaN'
    )
    updated = client.put(
        f"/api/blocks/model/{created.json()['id']}",
        content=raw_update,
        headers={"Content-Type": "application/json"},
    )
    listed = client.get("/api/blocks/model")

    assert updated.status_code == 422, updated.text
    assert listed.status_code == 200, listed.text
    assert [
        (item["name"], item["provider_settings"]["temperature"])
        for item in listed.json()
    ] == [
        ("Valid model", 0)
    ]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("temperature", "definitely-not-a-number"),
        ("max_completion_tokens", "4096"),
        ("max_completion_tokens", 0),
        ("seed", 1.5),
        ("timeout", 0),
        ("max_retries", -1),
        ("stream_usage", "true"),
        ("streaming", 1),
        ("reasoning_effort", False),
        ("service_tier", 1),
        ("logprobs", "false"),
        ("top_logprobs", -1),
    ],
)
def test_model_parameters_reject_wrong_types_and_impossible_values_before_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid: object,
) -> None:
    client = make_client(tmp_path, monkeypatch)
    payload = model_payload(f"Invalid {field}")
    payload["provider_settings"][field] = invalid

    response = client.post("/api/blocks/model", json=payload)

    assert response.status_code == 422, response.text
    assert client.get("/api/blocks/model").json() == []

def test_empty_text_is_an_explicit_override_where_the_middleware_allows_it(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)

    filesystem = client.post(
        "/api/blocks/filesystem",
        json={
            "name": "No file instructions",
            "system_prompt_override": "",
            "tool_configs": {
                "read_file": {"description_override": ""},
            },
        },
    )
    todo = client.post(
        "/api/blocks/todo-list",
        json={
            "name": "No todo instructions",
            "system_prompt_override": "",
            "tool_description_override": "",
        },
    )
    subagent = client.post(
        "/api/blocks/subagent",
        json={
            "name": "No delegation instructions",
            "instruction_override": "",
        },
    )

    assert filesystem.status_code == 200, filesystem.text
    assert filesystem.json()["system_prompt_override"] == ""
    assert filesystem.json()["tool_configs"]["read_file"]["description_override"] == ""
    assert todo.status_code == 200, todo.text
    assert todo.json()["system_prompt_override"] == ""
    assert todo.json()["tool_description_override"] == ""
    assert subagent.status_code == 200, subagent.text
    assert subagent.json()["instruction_override"] == ""
