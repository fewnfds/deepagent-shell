from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from agent_shell.python_packages.authoring import PythonPackageAuthoringService
from agent_shell.command_packages import CommandPackageRuntime, scan_command_package

from .app_support import make_client


def _write_router_template(data_root: Path, *, key: str = "basic_router") -> Path:
    folder = data_root / "templates" / "workflow" / "command" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.py").write_text(
        "def create_command():\n"
        "    branch = 'finish'\n"
        "    async def route(state, runtime):\n"
        "        return {'activate': [branch], 'update': {}}\n"
        "    return route\n",
        encoding="utf-8",
    )
    (folder / "requirements.txt").write_text("packaging==25.0\n", encoding="utf-8")
    (folder / "helpers" / "rules.py").parent.mkdir()
    (folder / "helpers" / "rules.py").write_text("VALUE = 1\n", encoding="utf-8")
    return folder


def _template_content(selected: dict, path: str) -> str:
    return next(
        (file["content"] for file in selected["files"] if file["path"] == path),
        "",
    )


def _create_command(
    client: TestClient,
    selected: dict,
    *,
    name: str,
    paths: list[str] | None = None,
) -> dict:
    editable_paths = paths or ["main.py"]
    response = client.post(
        "/api/blocks/command",
        json={
            "name": name,
            "python_package": {
                "folder": "",
                "editable_files": editable_paths,
            },
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [
                    {"path": path, "content": _template_content(selected, path)}
                    for path in editable_paths
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_repository_workflow_input_context_example_is_in_middleware_catalog(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[2]
    service = PythonPackageAuthoringService(
        templates_root=tmp_path / "templates",
        examples_root=repository / "examples",
        instances_root=tmp_path / "instances",
        runtime_root=tmp_path / "runtime",
    )

    response = service.template_catalog("custom-middleware")
    assert response["errors"] == {}
    template = response["catalog"][0]

    assert template["key"] == "内置示例-workflow-input-context"
    assert template["name"] == "内置示例-workflow-input-context"
    assert {file["path"] for file in template["files"]} == {
        "main.py",
        "requirements.txt",
    }


def test_repository_custom_tool_example_is_in_package_catalog(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[2]
    service = PythonPackageAuthoringService(
        templates_root=tmp_path / "templates",
        examples_root=repository / "examples",
        instances_root=tmp_path / "instances",
        runtime_root=tmp_path / "runtime",
    )

    response = service.template_catalog("custom-tool")
    assert response["errors"] == {}
    template = response["catalog"][0]

    assert template["key"] == "内置示例-default"
    assert template["family"] == "tool"
    assert template["adapter"] == "agent-tool"
    assert {file["path"] for file in template["files"]} == {
        "main.py",
        "requirements.txt",
    }


def test_empty_python_extension_adds_visible_requirements_file(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/blocks/custom-tool",
        json={
            "name": "Empty dependency tool",
            "python_package": {"folder": "", "editable_files": ["main.py"]},
            "python_package_files": {
                "template_key": "__empty__",
                "revision": "",
                "files": [{
                    "path": "main.py",
                    "content": (
                        "from langchain.tools import tool\n"
                        "@tool\n"
                        "def identity(value: str) -> str:\n"
                        "    \"\"\"Return value.\"\"\"\n"
                        "    return value\n"
                        "def create_tool():\n"
                        "    return identity\n"
                    ),
                }],
            },
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["python_package"]["editable_files"] == [
        "main.py", "requirements.txt"
    ]
    assert [file["path"] for file in created["python_package_files"]["files"]] == [
        "main.py", "requirements.txt"
    ]
    assert created["python_package_files"]["files"][-1]["content"] == ""


def test_manifest_free_template_creates_owned_package_and_keeps_missing_file_warning(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    template = _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)

    catalog_response = client.get("/api/python-package-templates/command")
    assert catalog_response.status_code == 200
    selected = catalog_response.json()["catalog"][0]
    assert selected["key"] == "basic_router"
    assert selected["name"] == "basic_router"
    assert [file["path"] for file in selected["files"]] == [
        "helpers/rules.py",
        "main.py",
        "requirements.txt",
    ]
    assert not (template / "template.json").exists()

    created = _create_command(
        client,
        selected,
        name="Private router",
        paths=["main.py", "helpers/rules.py", "missing.py"],
    )
    block_id = created["id"]
    folder_name = created["python_package"]["folder"]
    assert folder_name == block_id
    assert created["python_package"]["editable_files"] == [
        "main.py",
        "helpers/rules.py",
        "missing.py",
    ]
    assert created["python_package_files"]["files"][-1] == {
        "path": "missing.py",
        "content": "",
        "exists": False,
        "readable": True,
    }

    private_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "command"
        / folder_name
    )
    manifest = json.loads((private_folder / "package.json").read_text(encoding="utf-8"))
    assert manifest == {
        "format_version": 1,
        "family": "workflow-node",
        "adapter": "command",
        "id": folder_name,
    }
    assert not (private_folder / "missing.py").exists()
    stored = yaml.safe_load(
        (
            data_root
            / "config"
            / "components"
            / "command"
            / f"{block_id}.yaml"
        ).read_text(encoding="utf-8")
    )
    assert stored["payload"] == {
        "python_package": {
            "folder": folder_name,
            "editable_files": ["main.py", "helpers/rules.py", "missing.py"],
        }
    }


def test_loading_python_package_does_not_change_source_revision(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    template = _write_router_template(data_root)
    (template / "requirements.txt").write_text("", encoding="utf-8")
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"][0]
    created = _create_command(client, selected, name="Stable revision router")
    owner_id = created["id"]
    packages_dir = data_root / "config" / "python_package_instances"
    package_dir = packages_dir / "command" / owner_id
    before = scan_command_package(package_dir, owner_id=owner_id)["revision"]
    runtime = CommandPackageRuntime(
        request_id="revision-test",
        packages_dir=packages_dir,
        runtime_root=tmp_path / "runtime",
    )
    runtime.command_for(
        owner_id,
        owner_id,
        created["python_package"],
    )

    assert list(package_dir.rglob("*.pyc"))
    after = scan_command_package(package_dir, owner_id=owner_id)["revision"]
    assert after == before
    asyncio.run(runtime.close())


def test_builtin_example_coexists_with_same_named_user_template_and_is_copied(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root, key="shared-name")
    example = (
        tmp_path
        / "examples"
        / "workflow-components"
        / "command"
        / "shared-name"
    )
    example.mkdir(parents=True)
    example_source = (
        "def create_command():\n"
        "    async def route(state, runtime):\n"
        "        return {'activate': ['builtin'], 'update': {}}\n"
        "    return route\n"
    )
    (example / "main.py").write_text(example_source, encoding="utf-8")

    client = make_client(tmp_path, monkeypatch)
    catalog = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"]

    assert [item["key"] for item in catalog] == [
        "shared-name",
        "内置示例-shared-name",
    ]
    builtin = next(item for item in catalog if item["key"].startswith("内置示例-"))
    assert builtin["name"] == "内置示例-shared-name"

    created = _create_command(client, builtin, name="Built-in router")
    copied = (
        data_root
        / "config"
        / "python_package_instances"
        / "command"
        / created["id"]
        / "main.py"
    )
    assert copied.read_text(encoding="utf-8") == example_source


def test_command_can_be_created_from_empty_template_selection(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    source = (
        "def create_command():\n"
        "    async def route(state, runtime):\n"
        "        return {'activate': ['finish'], 'update': {}}\n"
        "    return route\n"
    )

    response = client.post(
        "/api/blocks/command",
        json={
            "name": "Empty template router",
            "python_package": {"folder": "", "editable_files": ["main.py"]},
            "python_package_files": {
                "template_key": "__empty__",
                "revision": "",
                "files": [{"path": "main.py", "content": source}],
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["python_package"]["folder"] == response.json()["id"]


def test_existing_package_updates_ordered_text_files_and_creates_new_file(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"][0]
    created = _create_command(client, selected, name="Editable router")
    loaded_files = client.post(
        f"/api/blocks/command/{created['id']}/python-package-files",
        json={"paths": ["helpers/rules.py", "missing.py"]},
    )
    assert loaded_files.status_code == 200, loaded_files.text
    assert loaded_files.json()["files"] == [
        {
            "path": "helpers/rules.py",
            "content": "VALUE = 1\n",
            "exists": True,
            "readable": True,
        },
        {"path": "missing.py", "content": "", "exists": False, "readable": True},
    ]
    updated_source = _template_content(selected, "main.py").replace(
        "'update': {}", "'update': {'shared_vars': {'edited': True}}"
    )
    response = client.put(
        f"/api/blocks/command/{created['id']}",
        json={
            "name": created["name"],
            "python_package": {
                "folder": created["python_package"]["folder"],
                "editable_files": ["helpers/rules.py", "main.py", "nested/new.py"],
            },
            "python_package_files": {
                "template_key": "",
                "revision": created["python_package_files"]["revision"],
                "files": [
                    {"path": "helpers/rules.py", "content": "VALUE = 2\n"},
                    {"path": "main.py", "content": updated_source},
                    {"path": "nested/new.py", "content": "ENABLED = True\n"},
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert [file["path"] for file in updated["python_package_files"]["files"]] == [
        "helpers/rules.py",
        "main.py",
        "nested/new.py",
    ]
    folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "command"
        / updated["python_package"]["folder"]
    )
    assert (folder / "nested" / "new.py").read_text(encoding="utf-8") == "ENABLED = True\n"

    conflict = client.put(
        f"/api/blocks/command/{created['id']}",
        json={
            "name": created["name"],
            "python_package": updated["python_package"],
            "python_package_files": {
                "template_key": "",
                "revision": created["python_package_files"]["revision"],
                "files": [
                    {"path": file["path"], "content": file["content"]}
                    for file in updated["python_package_files"]["files"]
                ],
            },
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "python_package_revision_conflict"


def test_editable_file_paths_cannot_escape_owned_package(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"][0]

    response = client.post(
        "/api/blocks/command",
        json={
            "name": "Escaping router",
            "python_package": {
                "folder": "",
                "editable_files": ["../outside.py"],
            },
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [{"path": "../outside.py", "content": "VALUE = 1\n"}],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "python_package_file_path_invalid"
    assert not (data_root / "config" / "python_package_instances" / "outside.py").exists()

    managed_manifest = client.post(
        "/api/blocks/command",
        json={
            "name": "Manifest editor",
            "python_package": {
                "folder": "",
                "editable_files": ["PACKAGE.JSON"],
            },
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [{"path": "PACKAGE.JSON", "content": "{}\n"}],
            },
        },
    )
    assert managed_manifest.status_code == 422
    assert managed_manifest.json()["detail"]["code"] == "python_package_file_path_invalid"


def test_legacy_python_package_config_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"][0]

    response = client.post(
        "/api/blocks/command",
        json={
            "name": "Legacy router",
            "python_package": {
                "folder": "",
                "editable_files": ["main.py"],
                "config": {"threshold": 80},
            },
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [
                    {
                        "path": "main.py",
                        "content": _template_content(selected, "main.py"),
                    }
                ],
            },
        },
    )

    assert response.status_code == 422
    instance_root = data_root / "config" / "python_package_instances" / "command"
    assert not instance_root.exists() or not any(instance_root.iterdir())


def test_copy_and_delete_follow_private_package_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/command"
    ).json()["catalog"][0]
    created = _create_command(client, selected, name="Source router")

    copied_response = client.post(
        f"/api/blocks/command/{created['id']}/copy",
        json={"name": "Copied router"},
    )
    assert copied_response.status_code == 200, copied_response.text
    copied = copied_response.json()
    assert copied["python_package"]["editable_files"] == ["main.py"]
    copied_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "command"
        / copied["python_package"]["folder"]
    )
    assert copied_folder.is_dir()
    assert client.delete(f"/api/blocks/command/{copied['id']}").status_code == 200
    assert not copied_folder.exists()
