from __future__ import annotations

import json
from pathlib import Path
import shutil

import yaml
from fastapi.testclient import TestClient

from agent_shell.python_packages.authoring import PythonPackageAuthoringService

from .app_support import make_client


def _write_router_template(data_root: Path, *, key: str = "basic_router") -> Path:
    folder = data_root / "templates" / "workflow" / "condition_router" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "template.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "family": "workflow-node",
                "adapter": "condition-router",
                "name": "Basic router",
                "description": "Routes with a configurable branch.",
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "branch": {
                            "type": "string",
                            "title": "Branch",
                            "default": "otherwise",
                        }
                    },
                    "required": ["branch"],
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(
        "def create_router(config):\n"
        "    async def route(state, context):\n"
        "        return {'activate': [config['branch']], 'update': {}}\n"
        "    return route\n",
        encoding="utf-8",
    )
    (folder / "requirements.txt").write_text("packaging==25.0\n", encoding="utf-8")
    (folder / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    return folder


def _create_router(
    client: TestClient,
    selected: dict,
    *,
    name: str,
    branch: str = "otherwise",
    requirements_source: str = "",
) -> dict:
    response = client.post(
        "/api/blocks/condition-router",
        json={
            "name": name,
            "python_package": {"folder": "", "config": {"branch": branch}},
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "main_source": selected["main_source"],
                "requirements_source": requirements_source,
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_template_is_inert_and_new_configuration_owns_a_private_copy(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    template = _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)

    catalog_response = client.get("/api/python-package-templates/condition-router")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()["catalog"]
    assert len(catalog) == 1
    selected = catalog[0]
    assert selected["key"] == "basic_router"
    assert "dependency_status" not in selected
    assert "requirements_fingerprint" not in selected
    assert template.is_dir()

    missing_template = client.post(
        "/api/blocks/condition-router",
        json={
            "name": "Missing template router",
            "python_package": {"folder": "", "config": {}},
            "python_package_files": {
                "template_key": "",
                "revision": "",
                "main_source": "",
                "requirements_source": "",
            },
        },
    )
    assert missing_template.status_code == 422
    assert missing_template.json()["detail"]["code"] == "python_package_template_required"

    created = _create_router(
        client,
        selected,
        name="Private router",
        branch="review",
        requirements_source=selected["requirements_source"],
    )
    block_id = created["id"]
    folder_name = created["python_package"]["folder"]
    assert folder_name.startswith(f"{block_id}--basic-router--")
    assert created["dependency_status"] == "restart_required"

    private_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / folder_name
    )
    assert (private_folder / "package.json").is_file()
    assert not (private_folder / "template.json").exists()
    assert (private_folder / "helper.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    instance_manifest = json.loads(
        (private_folder / "package.json").read_text(encoding="utf-8")
    )
    assert instance_manifest["id"] == folder_name.rsplit("--", 1)[1]

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
            "config": {"branch": "review"},
        }
    }
    assert "python_package_files" not in stored["payload"]


def test_existing_configuration_updates_files_without_replacing_its_package(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]
    created = _create_router(
        client,
        selected,
        name="Editable router",
        requirements_source=selected["requirements_source"],
    )
    block_id = created["id"]
    folder_name = created["python_package"]["folder"]
    private_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / folder_name
    )

    updated_source = created["python_package_files"]["main_source"].replace(
        "'update': {}", "'update': {'shared_vars': {'edited': True}}"
    )
    updated_response = client.put(
        f"/api/blocks/condition-router/{block_id}",
        json={
            "name": "Editable router",
            "python_package": {
                "folder": folder_name,
                "config": {"branch": "review"},
            },
            "python_package_files": {
                "template_key": "",
                "revision": created["python_package_files"]["revision"],
                "main_source": updated_source,
                "requirements_source": "",
            },
        },
    )
    assert updated_response.status_code == 200, updated_response.text
    updated = updated_response.json()
    assert updated["python_package"]["folder"] == folder_name
    assert (private_folder / "main.py").read_text(encoding="utf-8") == updated_source
    assert not (private_folder / "requirements.txt").exists()
    assert (private_folder / "helper.py").is_file()

    conflict = client.put(
        f"/api/blocks/condition-router/{block_id}",
        json={
            "name": "Editable router",
            "python_package": updated["python_package"],
            "python_package_files": {
                "template_key": "",
                "revision": created["python_package_files"]["revision"],
                "main_source": updated_source,
                "requirements_source": "",
            },
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "python_package_revision_conflict"


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
    assert copied["id"] != created["id"]
    assert copied["python_package"]["folder"] != created["python_package"]["folder"]
    assert copied["python_package"]["folder"].startswith(f"{copied['id']}--")

    copied_folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / copied["python_package"]["folder"]
    )
    assert copied_folder.is_dir()
    deleted = client.delete(f"/api/blocks/condition-router/{copied['id']}")
    assert deleted.status_code == 200
    assert not copied_folder.exists()


def test_invalid_prescribed_files_can_be_repaired_or_deleted(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]
    created = _create_router(client, selected, name="Repairable router")
    folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / created["python_package"]["folder"]
    )
    broken_source = "def create_router(config):\n    return (\n"
    (folder / "main.py").write_text(broken_source, encoding="utf-8")

    projected_response = client.get(
        f"/api/blocks/condition-router/{created['id']}"
    )
    assert projected_response.status_code == 200, projected_response.text
    projected = projected_response.json()
    assert projected["python_package_files"]["main_source"] == broken_source
    assert projected["python_package_error"]["message_key"] == "resource.error.pythonPackage.syntax"
    repaired_response = client.put(
        f"/api/blocks/condition-router/{created['id']}",
        json={
            "name": created["name"],
            "python_package": created["python_package"],
            "python_package_files": {
                "template_key": "",
                "revision": projected["python_package_files"]["revision"],
                "main_source": selected["main_source"],
                "requirements_source": "",
            },
        },
    )
    assert repaired_response.status_code == 200, repaired_response.text
    assert repaired_response.json()["python_package_error"] is None

    damaged = client.post(
        f"/api/blocks/condition-router/{created['id']}/copy",
        json={"name": "Damaged router"},
    ).json()
    damaged_folder = folder.parent / damaged["python_package"]["folder"]
    (damaged_folder / "requirements.txt").write_text(
        "--invalid-option\n", encoding="utf-8"
    )
    deleted_damaged = client.delete(
        f"/api/blocks/condition-router/{damaged['id']}"
    )
    assert deleted_damaged.status_code == 200, deleted_damaged.text
    assert not damaged_folder.exists()

    invalid_reference = client.post(
        f"/api/blocks/condition-router/{created['id']}/copy",
        json={"name": "Invalid reference router"},
    ).json()
    invalid_reference_folder = (
        folder.parent / invalid_reference["python_package"]["folder"]
    )
    config_path = (
        data_root
        / "config"
        / "components"
        / "condition-router"
        / f"{invalid_reference['id']}.yaml"
    )
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_config["payload"]["python_package"] = None
    config_path.write_text(yaml.safe_dump(raw_config), encoding="utf-8")
    client.close()
    client = make_client(tmp_path, monkeypatch)
    deleted_invalid_reference = client.delete(
        f"/api/blocks/condition-router/{invalid_reference['id']}"
    )
    assert deleted_invalid_reference.status_code == 200, deleted_invalid_reference.text
    assert invalid_reference_folder.is_dir()

    shutil.rmtree(folder)
    deleted_missing = client.delete(
        f"/api/blocks/condition-router/{created['id']}"
    )
    assert deleted_missing.status_code == 200, deleted_missing.text


def test_revision_conflict_does_not_restore_an_external_edit(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    _write_router_template(data_root)
    client = make_client(tmp_path, monkeypatch)
    selected = client.get(
        "/api/python-package-templates/condition-router"
    ).json()["catalog"][0]
    created = _create_router(client, selected, name="Conflict router")
    folder = (
        data_root
        / "config"
        / "python_package_instances"
        / "condition-router"
        / created["python_package"]["folder"]
    )
    external_source = created["python_package_files"]["main_source"].replace(
        "return route", "return route  # external edit"
    )
    original_inspect = PythonPackageAuthoringService._inspect_instance
    calls = 0

    def inspect_with_external_edit(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            (folder / "main.py").write_text(external_source, encoding="utf-8")
        return original_inspect(self, *args, **kwargs)

    monkeypatch.setattr(
        PythonPackageAuthoringService,
        "_inspect_instance",
        inspect_with_external_edit,
    )
    response = client.put(
        f"/api/blocks/condition-router/{created['id']}",
        json={
            "name": created["name"],
            "python_package": created["python_package"],
            "python_package_files": {
                "template_key": "",
                "revision": created["python_package_files"]["revision"],
                "main_source": selected["main_source"],
                "requirements_source": "",
            },
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "python_package_revision_conflict"
    assert (folder / "main.py").read_text(encoding="utf-8") == external_source
