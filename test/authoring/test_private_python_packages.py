from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from .app_support import make_client


def _write_router_template(data_root: Path, *, key: str = "basic_router") -> Path:
    folder = data_root / "templates" / "workflow" / "condition_router" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.py").write_text(
        "def create_router():\n"
        "    branch = 'otherwise'\n"
        "    async def route(state, context):\n"
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


def _create_router(
    client: TestClient,
    selected: dict,
    *,
    name: str,
    paths: list[str] | None = None,
) -> dict:
    editable_paths = paths or ["main.py"]
    response = client.post(
        "/api/blocks/condition-router",
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


def test_manifest_free_template_creates_owned_package_and_keeps_missing_file_warning(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    template = _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)

    catalog_response = client.get("/api/python-package-templates/condition-router")
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

    created = _create_router(
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
        / "condition-router"
        / folder_name
    )
    manifest = json.loads((private_folder / "package.json").read_text(encoding="utf-8"))
    assert manifest == {
        "format_version": 1,
        "family": "workflow-node",
        "adapter": "condition-router",
        "id": folder_name,
    }
    assert not (private_folder / "missing.py").exists()
    stored = yaml.safe_load(
        (
            data_root
            / "config"
            / "components"
            / "condition-router"
            / f"{block_id}.yaml"
        ).read_text(encoding="utf-8")
    )
    assert stored["payload"] == {
        "python_package": {
            "folder": folder_name,
            "editable_files": ["main.py", "helpers/rules.py", "missing.py"],
        }
    }


def test_condition_router_can_be_created_from_empty_template_selection(
    tmp_path: Path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    source = (
        "def create_router():\n"
        "    async def route(state, context):\n"
        "        return {'activate': ['otherwise'], 'update': {}}\n"
        "    return route\n"
    )

    response = client.post(
        "/api/blocks/condition-router",
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
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]
    created = _create_router(client, selected, name="Editable router")
    loaded_files = client.post(
        f"/api/blocks/condition-router/{created['id']}/python-package-files",
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
        f"/api/blocks/condition-router/{created['id']}",
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
        / "condition-router"
        / updated["python_package"]["folder"]
    )
    assert (folder / "nested" / "new.py").read_text(encoding="utf-8") == "ENABLED = True\n"

    conflict = client.put(
        f"/api/blocks/condition-router/{created['id']}",
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
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]

    response = client.post(
        "/api/blocks/condition-router",
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
        "/api/blocks/condition-router",
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
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]

    response = client.post(
        "/api/blocks/condition-router",
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
    instance_root = data_root / "config" / "python_package_instances" / "condition-router"
    assert not instance_root.exists() or not any(instance_root.iterdir())


def test_copy_and_delete_follow_private_package_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]
    created = _create_router(client, selected, name="Source router")

    copied_response = client.post(
        f"/api/blocks/condition-router/{created['id']}/copy",
        json={"name": "Copied router"},
    )
    assert copied_response.status_code == 200, copied_response.text
    copied = copied_response.json()
    assert copied["python_package"]["editable_files"] == ["main.py"]
    copied_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / copied["python_package"]["folder"]
    )
    assert copied_folder.is_dir()
    assert client.delete(f"/api/blocks/condition-router/{copied['id']}").status_code == 200
    assert not copied_folder.exists()
