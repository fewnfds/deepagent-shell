from __future__ import annotations

from .app_support import *


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
    subagent = client.post(
        "/api/blocks/subagent",
        json={
            "name": "Invalid task description",
            "task_description_override": "{available_agents}\n{unknown}",
        },
    )
    missing_catalog = client.post(
        "/api/blocks/subagent",
        json={
            "name": "Missing available agents",
            "task_description_override": "Delegate a complete task.",
        },
    )
    empty_format_spec = client.post(
        "/api/blocks/subagent",
        json={
            "name": "Empty format spec",
            "task_description_override": "Agents: {available_agents:}",
        },
    )
    assert skill.status_code == 422
    assert subagent.status_code == 422
    assert missing_catalog.status_code == 422
    assert empty_format_spec.status_code == 422


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
    subagent = client.post(
        "/api/blocks/subagent",
        json={
            "name": "Escaped task description",
            "task_description_override": (
                'JSON {{"answer": "value"}}\n{available_agents}'
            ),
        },
    )
    assert skill.status_code == 200, skill.text
    assert subagent.status_code == 200, subagent.text
    template = (
        tmp_path
        / "data"
        / "templates"
        / "agent"
        / "custom_middleware"
        / "syntax-check"
    )
    template.mkdir(parents=True, exist_ok=True)
    (template / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "family": "middleware",
                "adapter": "agent-middleware",
                "name": "Syntax check",
                "description": "Test template.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    valid_source = (
        "from langchain.agents.middleware import AgentMiddleware\n"
        "def create_middleware(config, agent):\n"
        "    return AgentMiddleware()\n"
    )
    (template / "main.py").write_text(valid_source, encoding="utf-8")
    selected = client.get(
        "/api/python-package-templates/middleware"
    ).json()["catalog"][0]
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
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": "middleware = (",
                    "requirements_source": "",
                },
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/blocks/custom-middleware",
            json={
                "name": "missing output",
                "python_package": {"folder": "", "config": {}},
                "python_package_files": {
                    "template_key": selected["key"],
                    "revision": selected["revision"],
                    "main_source": "value = object()\n",
                    "requirements_source": "",
                },
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
            "/api/main-agents",
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
            "/api/subagents",
            json={
                "id": "client-id",
                **subagent_payload("Bad client id", name="bad_id"),
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/subagents",
            json=subagent_payload(
                "Explicit inherit",
                name="explicit_inherit",
                capability_overrides=[
                    {"type": "model", "mode": "inherit", "block_id": ""}
                ],
            ),
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
