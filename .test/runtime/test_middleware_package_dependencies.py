from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_shell.middleware_packages import dependencies
from agent_shell.middleware_packages.dependencies import prepare_windows_dependencies
from agent_shell.middleware_packages.packages import scan_middleware_packages


def write_package(root: Path, package_id: str) -> Path:
    folder = root / package_id
    folder.mkdir(parents=True)
    (folder / "middleware.json").write_text(
        json.dumps(
            {
                "api_version": 1,
                "id": package_id,
                "name": package_id,
                "description": "Dependency test package.",
                "config_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            }
        ),
        encoding="utf-8",
    )
    (folder / "main.py").write_text(
        "from langchain.agents.middleware import AgentMiddleware\n"
        "def create_middleware(ctx):\n"
        "    return AgentMiddleware()\n",
        encoding="utf-8",
    )
    return folder


def write_runtime_manifest(runtime_root: Path) -> None:
    manifest = runtime_root / "app" / "runtime-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "platform": "windows-x64",
                "python": "3.12.9",
                "uv": "0.11.28",
                "uv_url": "https://example.invalid/uv.zip",
                "uv_sha256": "0" * 64,
                "build_fingerprint": "core-fingerprint",
            }
        ),
        encoding="utf-8",
    )


def test_requirements_are_normalized_and_need_runtime_state(tmp_path: Path) -> None:
    packages = tmp_path / "packages"
    folder = write_package(packages, "image-reader")
    (folder / "requirements.txt").write_text(
        "# package dependencies\nPillow>=11,<13\nhttpx; python_version >= '3.12'\n",
        encoding="utf-8",
    )

    catalog = scan_middleware_packages(packages)["catalog"]

    assert catalog[0]["python_requirements"] == [
        'httpx; python_version >= "3.12"',
        "Pillow<13,>=11",
    ]
    assert catalog[0]["dependency_status"] == "restart_required"

    (folder / "requirements.txt").write_text(
        "--extra-index-url https://packages.example/simple\n",
        encoding="utf-8",
    )
    invalid = scan_middleware_packages(packages)
    assert invalid["catalog"] == []
    assert invalid["errors"]["image-reader"]["message_key"] == (
        "resource.error.middlewarePackage.requirementsInvalid"
    )


def test_dependency_preparation_replaces_only_successful_package_layer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    runtime_root = tmp_path / "runtime"
    packages = data_root / "resources" / "custom_middlewares"
    folder = write_package(packages, "image-reader")
    (folder / "requirements.txt").write_text("Pillow==12.0.0\n", encoding="utf-8")
    write_runtime_manifest(runtime_root)
    fake_uv = tmp_path / "uv.exe"
    fake_uv.write_bytes(b"fake")
    monkeypatch.setattr(dependencies, "_ensure_uv", lambda *_args: fake_uv)
    monkeypatch.setattr(dependencies, "_core_constraints", lambda: ("pydantic==2.12.5",))
    calls: list[list[str]] = []

    def successful_install(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(arguments)
        target = Path(arguments[arguments.index("--target") + 1])
        (target / "PIL").mkdir()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dependencies.subprocess, "run", successful_install)
    prepare_windows_dependencies(data_root=data_root, runtime_root=runtime_root)

    state = dependencies.load_dependency_state(runtime_root)
    assert state is not None
    assert state["status"] == "ready"
    assert state["packages"]["image-reader"]["status"] == "ready"
    assert (dependencies.package_site_packages(runtime_root) / "PIL").is_dir()
    assert "--only-binary" in calls[0]
    ready = scan_middleware_packages(packages, runtime_root=runtime_root)["catalog"]
    assert ready[0]["dependency_status"] == "ready"

    monkeypatch.setattr(
        dependencies.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    (folder / "requirements.txt").write_text("Pillow==13.0.0\n", encoding="utf-8")
    prepare_windows_dependencies(data_root=data_root, runtime_root=runtime_root)

    failed_state = dependencies.load_dependency_state(runtime_root)
    assert failed_state is not None
    assert failed_state["status"] == "failed"
    assert failed_state["packages"]["image-reader"]["status"] == "failed"
    assert (dependencies.package_site_packages(runtime_root) / "PIL").is_dir()
    failed = scan_middleware_packages(packages, runtime_root=runtime_root)["catalog"]
    assert failed[0]["dependency_status"] == "failed"
