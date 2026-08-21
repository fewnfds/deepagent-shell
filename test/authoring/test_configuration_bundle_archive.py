from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from agent_shell.configuration.bundles.archive import (
    BundleArchiveError,
    build_bundle,
    canonical_json_bytes,
    canonical_tree_sha256,
    parse_bundle,
)
from agent_shell.configuration.bundles.contracts import (
    BundleManifest,
    BundleRecord,
    BundleRoot,
    SkillPackageAsset,
)


SOURCE_ID = "11111111-1111-4111-8111-111111111111"


def _manifest(*, skill: bool = False) -> tuple[BundleManifest, dict[str, bytes]]:
    files: dict[str, bytes] = {}
    assets = []
    payload: dict[str, object]
    if skill:
        content = (
            b"---\nname: outline\ndescription: Build an outline.\n---\n\nSteps.\n"
        )
        tree = {"outline/SKILL.md": content}
        files = {f"assets/skill-packages/{SOURCE_ID}/outline/SKILL.md": content}
        assets = [
            SkillPackageAsset(
                kind="skill-package",
                owner_source_id=SOURCE_ID,
                path=f"assets/skill-packages/{SOURCE_ID}/",
                sha256=canonical_tree_sha256(tree),
            )
        ]
        payload = {
            "skill_package": {"folder": SOURCE_ID},
            "system_prompt_enabled": True,
            "instruction_override": None,
        }
        component_type = "skill"
    else:
        payload = {"system_prompt": "Be precise."}
        component_type = "system-prompt"
    root = BundleRoot(kind="component", type=component_type, source_id=SOURCE_ID)
    return (
        BundleManifest(
            source_application_version="0.2.0",
            root=root,
            records=[
                BundleRecord(
                    kind="component",
                    type=component_type,
                    source_id=SOURCE_ID,
                    name="Portable configuration",
                    payload=payload,
                )
            ],
            assets=assets,
        ),
        files,
    )


def _rewrite_entry(bundle: bytes, name: str, content: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(bundle)) as source, ZipFile(output, "w") as target:
        for info in source.infolist():
            target.writestr(
                info,
                content if info.filename == name else source.read(info),
            )
    return output.getvalue()


def test_bundle_archive_is_deterministic_and_hashes_canonical_content() -> None:
    manifest, files = _manifest(skill=True)

    first = build_bundle(manifest, files)
    second = build_bundle(manifest, files)
    parsed = parse_bundle(first)

    assert first == second
    assert parsed.bundle_sha256 == sha256(first).hexdigest()
    assert parsed.manifest_sha256 == sha256(
        canonical_json_bytes(manifest.model_dump(mode="json", by_alias=True))
    ).hexdigest()
    assert parsed.manifest == manifest


def test_bundle_archive_rejects_path_traversal_unknown_version_and_asset_tampering() -> None:
    manifest, files = _manifest(skill=True)
    bundle = build_bundle(manifest, files)

    unsafe = BytesIO(bundle)
    with ZipFile(unsafe, "a") as archive:
        archive.writestr("../outside.txt", b"outside")
    with pytest.raises(BundleArchiveError, match="unsafe segment"):
        parse_bundle(unsafe.getvalue())

    conflicting = BytesIO(bundle)
    with ZipFile(conflicting, "a") as archive:
        prefix = f"assets/skill-packages/{SOURCE_ID}/outline/"
        archive.writestr(f"{prefix}nested", b"file")
        archive.writestr(f"{prefix}nested/child.txt", b"child")
    with pytest.raises(BundleArchiveError, match="files and directories"):
        parse_bundle(conflicting.getvalue())

    raw_manifest = manifest.model_dump(mode="json", by_alias=True)
    raw_manifest["format_version"] = 1
    unknown_version = _rewrite_entry(
        bundle,
        "manifest.json",
        canonical_json_bytes(raw_manifest),
    )
    with pytest.raises(BundleArchiveError, match="current contract"):
        parse_bundle(unknown_version)

    tampered = _rewrite_entry(
        bundle,
        f"assets/skill-packages/{SOURCE_ID}/outline/SKILL.md",
        b"different",
    )
    with pytest.raises(BundleArchiveError, match="hash"):
        parse_bundle(tampered)
