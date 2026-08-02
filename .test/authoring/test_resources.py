from __future__ import annotations

from .app_support import *

def test_custom_tool_catalog_scans_source_without_importing_it(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    tools_dir = tmp_path / "data" / "resources" / "custom_tools"
    marker = tmp_path / "must-not-exist.txt"
    (tools_dir / "safe_tool.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "from langchain.tools import tool\n"
        "@tool('count_words')\n"
        "def word_count(text: str) -> int:\n"
        '    """Count words."""\n'
        "    return len(text.split())\n",
        encoding="utf-8",
    )
    (tools_dir / "bad name.py").write_text(
        "from langchain.tools import tool\n"
        "@tool\n"
        "def valid_shape(value: str) -> str:\n"
        '    """Valid except for its resource filename."""\n'
        "    return value\n",
        encoding="utf-8",
    )
    (tools_dir / "missing_annotations.py").write_text(
        "from langchain.tools import tool\n"
        "@tool\n"
        "def untyped(value):\n"
        '    """Missing an input annotation."""\n'
        "    return value\n",
        encoding="utf-8",
    )
    (tools_dir / "missing_description.py").write_text(
        "from langchain.tools import tool\n"
        "@tool\n"
        "def undescribed(value: str) -> str:\n"
        "    return value\n",
        encoding="utf-8",
    )
    (tools_dir / "schema_tool.py").write_text(
        "from langchain.tools import tool\n"
        "from pydantic import BaseModel\n"
        "class SchemaInput(BaseModel):\n"
        "    value: str\n"
        "@tool(args_schema=SchemaInput, description='Schema-backed tool.')\n"
        "def schema_tool(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    response = client.get("/api/tools/custom")
    assert response.status_code == 200
    result = response.json()
    assert [item["name"] for item in result["catalog"]] == [
        "safe_tool",
        "schema_tool",
    ]
    assert result["catalog"][0]["function"] == "word_count"
    assert result["catalog"][0]["tool_name"] == "count_words"
    assert "origin" not in result["catalog"][0]
    assert result["catalog"][1]["tool_name"] == "schema_tool"
    assert result["catalog"][1]["description"] == "Schema-backed tool."
    assert set(result["errors"]) == {
        "bad name.py",
        "missing_annotations.py",
        "missing_description.py",
    }
    assert result["errors"]["bad name.py"] == {
        "message_key": "resource.error.customTool.invalidName",
        "message_args": {"max_length": 120},
    }
    assert result["errors"]["missing_annotations.py"] == {
        "message_key": "resource.error.customTool.parameterAnnotationsRequired",
        "message_args": {
            "function_name": "untyped",
            "parameter_names": "value",
        },
    }
    assert result["errors"]["missing_description.py"] == {
        "message_key": "resource.error.customTool.descriptionRequired",
        "message_args": {"function_name": "undescribed"},
    }
    assert not marker.exists()

def test_skill_catalog_enforces_current_deepagents_metadata_contract(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    skills_dir = tmp_path / "data" / "resources" / "skills"
    valid = skills_dir / "valid-skill"
    valid.mkdir(parents=True)
    (valid / "SKILL.md").write_text(
        "---\n"
        "name: valid-skill\n"
        "description: A valid Skill.\n"
        "extra: &loop\n"
        "  - *loop\n"
        "score: .nan\n"
        "---\n",
        encoding="utf-8",
    )
    missing_description = skills_dir / "missing-description"
    missing_description.mkdir()
    (missing_description / "SKILL.md").write_text(
        "---\nname: missing-description\n---\n",
        encoding="utf-8",
    )
    invalid_name = skills_dir / "Invalid_Name"
    invalid_name.mkdir()
    (invalid_name / "SKILL.md").write_text(
        "---\nname: Invalid_Name\ndescription: Invalid name.\n---\n",
        encoding="utf-8",
    )

    response = client.get("/api/skills")

    assert response.status_code == 200
    result = response.json()
    assert [item["name"] for item in result["catalog"]] == ["valid-skill"]
    assert result["catalog"][0] == {
        "name": "valid-skill",
        "folder": "valid-skill",
        "description": "A valid Skill.",
    }
    assert set(result["errors"]) == {"Invalid_Name", "missing-description"}
    assert result["errors"]["Invalid_Name"] == {
        "message_key": "resource.error.skill.nameCharacters",
        "message_args": {},
    }
    assert result["errors"]["missing-description"] == {
        "message_key": "resource.error.skill.descriptionMissing",
        "message_args": {},
    }

def test_custom_middleware_catalog_scans_recipes_without_executing_them(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    middlewares_dir = tmp_path / "data" / "resources" / "custom_middlewares"
    marker = tmp_path / "middleware-must-not-exist.txt"
    source = (
        '"""Safe middleware recipe."""\n'
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "middleware = object()\n"
    )
    (middlewares_dir / "safe_recipe.py").write_text(source, encoding="utf-8")
    (middlewares_dir / "missing_output.py").write_text(
        "value = object()\n", encoding="utf-8"
    )
    (middlewares_dir / "bad_syntax.py").write_text(
        "middleware = (\n", encoding="utf-8"
    )

    response = client.get("/api/middlewares/custom")

    assert response.status_code == 200
    result = response.json()
    assert result["catalog"] == [
        {
            "name": "safe_recipe",
            "filename": "safe_recipe.py",
            "description": "Safe middleware recipe.",
            "source": source,
        }
    ]
    assert set(result["errors"]) == {"bad_syntax.py", "missing_output.py"}
    assert result["errors"]["bad_syntax.py"] == {
        "message_key": "resource.error.customMiddleware.syntax",
        "message_args": {"line": 1},
    }
    assert result["errors"]["missing_output.py"] == {
        "message_key": "resource.error.customMiddleware.bindingRequired",
        "message_args": {},
    }
    assert not marker.exists()


def test_resource_catalogs_only_scan_the_data_root(
    tmp_path: Path, monkeypatch
) -> None:
    root_tools = tmp_path / "resources" / "custom_tools"
    root_middlewares = tmp_path / "resources" / "custom_middlewares"
    root_tools.mkdir(parents=True)
    root_middlewares.mkdir(parents=True)
    (root_tools / "ignored.py").write_text(
        "from langchain_core.tools import tool\n"
        "@tool\n"
        "def ignored(value: str) -> str:\n"
        "    \"\"\"This application-home tool must stay undiscoverable.\"\"\"\n"
        "    return value\n",
        encoding="utf-8",
    )
    (root_middlewares / "ignored.py").write_text(
        "middleware = object()\n",
        encoding="utf-8",
    )

    client = make_client(tmp_path, monkeypatch)

    assert client.get("/api/tools/custom").json() == {"catalog": [], "errors": {}}
    assert client.get("/api/middlewares/custom").json() == {
        "catalog": [],
        "errors": {},
    }


def test_saving_custom_middleware_source_does_not_execute_it(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    marker = tmp_path / "save-must-not-exist.txt"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "middleware = object()\n"
    )

    response = client.post(
        "/api/blocks/custom-middleware",
        json={
            "name": "Static only",
            "middlewares": [
                {"name": "side effect recipe", "enabled": True, "source": source}
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["middlewares"][0]["source"] == source.strip()
    assert not marker.exists()

def test_new_database_contains_current_authoring_and_api_server_tables(
    tmp_path: Path, monkeypatch
) -> None:
    make_client(tmp_path, monkeypatch)
    with closing(
        sqlite3.connect(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    ) as connection, connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert tables == {
        "blocks",
        "primary_agents",
        "subagent_overrides",
        "provider_secrets",
        "api_server_settings",
        "api_server_request_settings",
        "history_retention_settings",
        "runtime_control_settings",
        "system_log_settings",
        "interception_test_records",
        "api_message_history",
        "runtime_diagnostics",
        "agent_session_runs",
    }
