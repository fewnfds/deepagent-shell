from __future__ import annotations

import json

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
    packages_dir = tmp_path / "data" / "resources" / "python_packages"
    package_id = "11111111-1111-4111-8111-111111111111"
    marker = tmp_path / "middleware-must-not-exist.txt"
    source = (
        '"""Safe middleware package."""\n'
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "def create_middleware(config, agent):\n"
        "    return object()\n"
    )
    package_dir = packages_dir / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": package_id,
                "family": "middleware",
                "adapter": "agent-middleware",
                "name": "Safe recipe",
                "description": "Safe middleware package.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "main.py").write_text(source, encoding="utf-8")
    broken_dir = packages_dir / "broken-package"
    broken_dir.mkdir()
    (broken_dir / "package.json").write_text("{}", encoding="utf-8")

    response = client.get("/api/python-packages/middleware/agent-middleware")

    assert response.status_code == 200
    result = response.json()
    assert len(result["catalog"]) == 1
    item = result["catalog"][0]
    assert item["format_version"] == 1
    assert item["id"] == package_id
    assert item["family"] == "middleware"
    assert item["adapter"] == "agent-middleware"
    assert item["name"] == "Safe recipe"
    assert item["description"] == "Safe middleware package."
    assert item["config_schema"] == {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    assert item["folder"] == package_id
    assert item["python_requirements"] == []
    assert len(item["requirements_fingerprint"]) == 64
    assert item["dependency_status"] == "ready"
    assert item["dependency_error_code"] == ""
    assert set(result["errors"]) == {"broken-package"}
    assert result["errors"]["broken-package"]["message_key"] == (
        "resource.error.pythonPackage.filesRequired"
    )
    assert not marker.exists()

def test_resource_catalogs_only_scan_the_data_root(
    tmp_path: Path, monkeypatch
) -> None:
    root_tools = tmp_path / "resources" / "custom_tools"
    root_packages = tmp_path / "resources" / "python_packages"
    root_tools.mkdir(parents=True)
    root_packages.mkdir(parents=True)
    (root_tools / "ignored.py").write_text(
        "from langchain_core.tools import tool\n"
        "@tool\n"
        "def ignored(value: str) -> str:\n"
        "    \"\"\"This application-home tool must stay undiscoverable.\"\"\"\n"
        "    return value\n",
        encoding="utf-8",
    )
    (root_packages / "ignored.py").write_text(
        "middleware = object()\n",
        encoding="utf-8",
    )

    client = make_client(tmp_path, monkeypatch)

    assert client.get("/api/tools/custom").json() == {"catalog": [], "errors": {}}
    assert client.get("/api/python-packages/middleware/agent-middleware").json() == {
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
        "def create_middleware(config, agent):\n"
        "    return object()\n"
    )
    package_id = "22222222-2222-4222-8222-222222222222"
    package_dir = tmp_path / "data" / "resources" / "python_packages" / package_id
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "package.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "id": package_id,
                "family": "middleware",
                "adapter": "agent-middleware",
                "name": "Side effect",
                "description": "Static package.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "main.py").write_text(source, encoding="utf-8")

    response = client.post(
        "/api/blocks/custom-middleware",
        json={
            "name": "Static only",
            "python_package_bindings": [
                {"package_id": package_id, "enabled": True, "config": {}}
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["python_package_bindings"][0] == {
        "package_id": package_id,
        "enabled": True,
        "config": {},
    }
    assert not marker.exists()
