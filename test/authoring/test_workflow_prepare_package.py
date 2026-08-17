from __future__ import annotations

import json
from pathlib import Path

import yaml

from .app_support import make_client


def test_workflow_prepare_is_created_from_an_owned_python_package(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "data"
    template = data_root / "templates" / "workflow" / "prepare" / "basic"
    template.mkdir(parents=True)
    source = (
        "def create_prepare():\n"
        "    async def prepare(input):\n"
        "        return {'context': {'request_id': input['request']['request_id']}}\n"
        "    return prepare\n"
    )
    (template / "main.py").write_text(source, encoding="utf-8")

    client = make_client(tmp_path, monkeypatch)
    catalog_response = client.get(
        "/api/python-package-templates/workflow-prepare"
    )
    assert catalog_response.status_code == 200, catalog_response.text
    catalog = catalog_response.json()
    assert catalog["errors"] == {}
    selected = catalog["catalog"][0]
    assert selected["family"] == "workflow"
    assert selected["adapter"] == "workflow-prepare"

    response = client.post(
        "/api/blocks/workflow-prepare",
        json={
            "name": "Prepare request context",
            "python_package": {"folder": "", "editable_files": ["main.py"]},
            "python_package_files": {
                "template_key": selected["key"],
                "revision": selected["revision"],
                "files": [{"path": "main.py", "content": source}],
            },
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    block_id = created["id"]
    assert created["python_package"] == {
        "folder": block_id,
        "editable_files": ["main.py"],
    }
    assert created["python_package_manifest"] == {
        "format_version": 1,
        "id": block_id,
        "family": "workflow",
        "adapter": "workflow-prepare",
        "folder": block_id,
    }

    package_root = (
        data_root
        / "config"
        / "python_package_instances"
        / "workflow-prepare"
        / block_id
    )
    assert (package_root / "main.py").read_text(encoding="utf-8") == source
    assert json.loads(
        (package_root / "package.json").read_text(encoding="utf-8")
    ) == {
        "format_version": 1,
        "family": "workflow",
        "adapter": "workflow-prepare",
        "id": block_id,
    }
    stored = yaml.safe_load(
        (
            data_root
            / "config"
            / "components"
            / "workflow-prepare"
            / f"{block_id}.yaml"
        ).read_text(encoding="utf-8")
    )
    assert stored["name"] == "Prepare request context"
    assert stored["payload"] == {
        "python_package": {
            "folder": block_id,
            "editable_files": ["main.py"],
        }
    }

    copied_response = client.post(
        f"/api/blocks/workflow-prepare/{block_id}/copy",
        json={"name": "Copied Prepare"},
    )
    assert copied_response.status_code == 200, copied_response.text
    copied = copied_response.json()
    copied_root = (
        data_root
        / "config"
        / "python_package_instances"
        / "workflow-prepare"
        / copied["id"]
    )
    assert copied["id"] != block_id
    assert copied["python_package"]["folder"] == copied["id"]
    assert (copied_root / "main.py").read_text(encoding="utf-8") == source

    delete_response = client.delete(
        f"/api/blocks/workflow-prepare/{copied['id']}"
    )
    assert delete_response.status_code == 200, delete_response.text
    assert not copied_root.exists()
