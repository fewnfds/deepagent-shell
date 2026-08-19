from __future__ import annotations

import json

from .app_support import *

def test_custom_tool_template_catalog_scans_package_without_importing_it(
    tmp_path: Path, monkeypatch
) -> None:
    templates_dir = tmp_path / "data" / "templates" / "agent" / "custom_tool"
    marker = tmp_path / "must-not-exist.txt"
    safe = templates_dir / "safe-tool"
    safe.mkdir(parents=True)
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "from langchain.tools import tool\n"
        "@tool\n"
        "def word_count(text: str) -> int:\n"
        '    """Count words."""\n'
        "    return len(text.split())\n"
        "def create_tool():\n"
        "    return word_count\n"
    )
    (safe / "main.py").write_text(source, encoding="utf-8")
    (safe / "requirements.txt").write_text("", encoding="utf-8")
    (templates_dir / "broken-package").mkdir()
    client = make_client(tmp_path, monkeypatch)

    response = client.get("/api/python-package-templates/custom-tool")
    assert response.status_code == 200
    result = response.json()
    assert [item["name"] for item in result["catalog"]] == ["safe-tool"]
    assert result["catalog"][0]["family"] == "tool"
    assert result["catalog"][0]["adapter"] == "agent-tool"
    assert {item["path"] for item in result["catalog"][0]["files"]} == {
        "main.py",
        "requirements.txt",
    }
    assert set(result["errors"]) == {"broken-package"}
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
    templates_dir = tmp_path / "data" / "templates" / "agent" / "custom_middleware"
    marker = tmp_path / "middleware-must-not-exist.txt"
    source = (
        '"""Safe middleware package."""\n'
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "def create_middleware(agent):\n"
        "    return object()\n"
    )
    package_dir = templates_dir / "safe-recipe"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "main.py").write_text(source, encoding="utf-8")
    broken_dir = templates_dir / "broken-package"
    broken_dir.mkdir()

    client = make_client(tmp_path, monkeypatch)
    response = client.get("/api/python-package-templates/middleware")

    assert response.status_code == 200
    result = response.json()
    assert len(result["catalog"]) == 1
    item = result["catalog"][0]
    assert item["format_version"] == 1
    assert item["key"] == "safe-recipe"
    assert item["family"] == "middleware"
    assert item["adapter"] == "agent-middleware"
    assert item["name"] == "safe-recipe"
    assert item["files"] == [
        {"path": "main.py", "content": source, "exists": True}
    ]
    assert "requirements_fingerprint" not in item
    assert "dependency_status" not in item
    assert set(result["errors"]) == {"broken-package"}
    assert result["errors"]["broken-package"]["message_key"] == (
        "resource.error.pythonPackage.filesRequired"
    )
    assert not marker.exists()

def test_resource_catalogs_only_scan_the_data_root(
    tmp_path: Path, monkeypatch
) -> None:
    root_tools = tmp_path / "templates" / "agent" / "custom_tool" / "ignored"
    root_templates = tmp_path / "templates" / "agent" / "custom_middleware"
    root_tools.mkdir(parents=True)
    root_templates.mkdir(parents=True)
    (root_tools / "main.py").write_text(
        "from langchain_core.tools import tool\n"
        "@tool\n"
        "def ignored(value: str) -> str:\n"
        "    \"\"\"This application-home tool must stay undiscoverable.\"\"\"\n"
        "    return value\n",
        encoding="utf-8",
    )
    (root_templates / "ignored.py").write_text(
        "middleware = object()\n",
        encoding="utf-8",
    )

    client = make_client(tmp_path, monkeypatch)

    assert client.get("/api/python-package-templates/custom-tool").json() == {
        "catalog": [],
        "errors": {},
    }
    assert client.get("/api/python-package-templates/middleware").json() == {
        "catalog": [],
        "errors": {},
    }

def test_saving_custom_middleware_source_does_not_execute_it(
    tmp_path: Path, monkeypatch
) -> None:
    marker = tmp_path / "save-must-not-exist.txt"
    source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "def create_middleware(agent):\n"
        "    return object()\n"
    )
    package_dir = (
        tmp_path
        / "data"
        / "templates"
        / "agent"
        / "custom_middleware"
        / "side-effect"
    )
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "main.py").write_text(source, encoding="utf-8")
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/middleware"
    ).json()["catalog"][0]

    response = client.post(
        "/api/blocks/custom-middleware",
        json={
            "name": "Static only",
            "python_package": {"folder": "", "editable_files": ["main.py"]},
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [
                    {"path": file["path"], "content": file["content"]}
                    for file in selected["files"] if file["path"] == "main.py"
                ],
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["python_package"]["folder"] == response.json()["id"]
    assert not marker.exists()
