from __future__ import annotations

import json

from agent_shell.storage.file_config import FileConfigRepository

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
    skills_dir = tmp_path / "data" / "skills-template"
    valid = skills_dir / "group-a" / "valid-skill"
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
    duplicate = skills_dir / "group-b" / "valid-skill"
    duplicate.mkdir(parents=True)
    (duplicate / "SKILL.md").write_text(
        "---\nname: valid-skill\ndescription: Another valid Skill.\n---\n",
        encoding="utf-8",
    )
    missing_description = skills_dir / "broken" / "missing-description"
    missing_description.mkdir(parents=True)
    (missing_description / "SKILL.md").write_text(
        "---\nname: missing-description\n---\n",
        encoding="utf-8",
    )
    invalid_name = skills_dir / "broken" / "Invalid_Name"
    invalid_name.mkdir()
    (invalid_name / "SKILL.md").write_text(
        "---\nname: Invalid_Name\ndescription: Invalid name.\n---\n",
        encoding="utf-8",
    )
    boundary = skills_dir / "blocked"
    nested = boundary / "nested-skill"
    nested.mkdir(parents=True)
    boundary.joinpath("SKILL.md").write_text(
        "---\nname: other\ndescription: Invalid boundary.\n---\n",
        encoding="utf-8",
    )
    nested.joinpath("SKILL.md").write_text(
        "---\nname: nested-skill\ndescription: Must stay owned by parent.\n---\n",
        encoding="utf-8",
    )

    response = client.get("/api/skills")

    assert response.status_code == 200
    result = response.json()
    assert [item["name"] for item in result["catalog"]] == ["valid-skill", "valid-skill"]
    assert result["catalog"][0] == {
        "name": "valid-skill",
        "folder": "valid-skill",
        "description": "A valid Skill.",
        "template_path": "group-a/valid-skill",
    }
    assert result["catalog"][1]["template_path"] == "group-b/valid-skill"
    assert set(result["errors"]) == {
        "blocked", "broken/Invalid_Name", "broken/missing-description"
    }
    assert "blocked/nested-skill" not in result["errors"]
    assert result["errors"]["broken/Invalid_Name"] == {
        "message_key": "resource.error.skill.nameCharacters",
        "message_args": {},
    }
    assert result["errors"]["broken/missing-description"] == {
        "message_key": "resource.error.skill.descriptionMissing",
        "message_args": {},
    }


def test_skill_component_owns_private_copy_and_rejects_same_name_add(
    tmp_path: Path, monkeypatch
) -> None:
    templates = tmp_path / "data" / "skills-template"
    for group, text in (("first", "First body."), ("second", "Second body.")):
        folder = templates / group / "outline"
        folder.mkdir(parents=True)
        folder.joinpath("SKILL.md").write_text(
            f"---\nname: outline\ndescription: {group} outline.\n---\n\n{text}\n",
            encoding="utf-8",
        )
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/blocks/skill",
        json={"name": "Writing", "skill_template_paths": ["first/outline"]},
    )
    assert created.status_code == 200, created.text
    component = created.json()
    owner_id = component["id"]
    private_root = (
        FileConfigRepository(tmp_path / "data").skill_package_instances_root
        / owner_id
    )
    assert "First body." in private_root.joinpath("outline", "SKILL.md").read_text(
        encoding="utf-8"
    )

    conflict = client.post(
        f"/api/blocks/skill/{owner_id}/skills",
        json={"template_path": "second/outline"},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "skill_name_conflict"
    assert "First body." in private_root.joinpath("outline", "SKILL.md").read_text(
        encoding="utf-8"
    )

    removed = client.delete(f"/api/blocks/skill/{owner_id}/skills/outline")
    assert removed.status_code == 200, removed.text
    added = client.post(
        f"/api/blocks/skill/{owner_id}/skills",
        json={"template_path": "second/outline"},
    )
    assert added.status_code == 200, added.text
    assert "Second body." in private_root.joinpath("outline", "SKILL.md").read_text(
        encoding="utf-8"
    )

    private_root.joinpath("outline", "SKILL.md").write_text(
        "invalid user content\n", encoding="utf-8"
    )
    inspected = client.get(f"/api/blocks/skill/{owner_id}/skills")
    assert inspected.status_code == 200, inspected.text
    assert set(inspected.json()["warnings"]) == {"outline"}
    saved = client.put(
        f"/api/blocks/skill/{owner_id}",
        json={
            "name": "Writing",
            "skill_package": {"folder": owner_id},
            "system_prompt_enabled": True,
            "instruction_override": None,
        },
    )
    assert saved.status_code == 200, saved.text

    copied = client.post(
        f"/api/blocks/skill/{owner_id}/copy", json={"name": "Writing copy"}
    )
    assert copied.status_code == 200, copied.text
    copy_id = copied.json()["id"]
    assert (private_root.parent / copy_id / "outline" / "SKILL.md").is_file()
    deleted = client.delete(f"/api/blocks/skill/{copy_id}")
    assert deleted.status_code == 200, deleted.text
    assert not (private_root.parent / copy_id).exists()


def test_failed_skill_create_rolls_back_private_package(tmp_path: Path, monkeypatch) -> None:
    template = tmp_path / "data" / "skills-template" / "outline"
    template.mkdir(parents=True)
    template.joinpath("SKILL.md").write_text(
        "---\nname: outline\ndescription: Outline.\n---\n",
        encoding="utf-8",
    )
    client = make_client(tmp_path, monkeypatch)
    repository = FileConfigRepository(tmp_path / "data")
    before = set(repository.skill_package_instances_root.iterdir())
    response = client.post(
        "/api/blocks/skill",
        json={"name": "", "skill_template_paths": ["outline"]},
    )
    assert response.status_code == 422, response.text
    assert set(repository.skill_package_instances_root.iterdir()) == before

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
