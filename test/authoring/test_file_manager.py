from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from zipfile import ZipFile

import pytest

from .app_support import make_client


def test_file_manager_completes_common_file_and_text_workflows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        scopes = client.get("/api/file-manager")
        empty = client.get("/api/file-manager/files")
        created_directory = client.post(
            "/api/file-manager/files/directories",
            json={"path": "notes/drafts"},
        )
        created_file = client.post(
            "/api/file-manager/files/text-files",
            json={"path": "notes/drafts/idea.txt"},
        )
        client.post(
            "/api/file-manager/files/directories",
            json={"path": "notes/empty"},
        )
        opened = client.get(
            "/api/file-manager/files/text",
            params={"path": "notes/drafts/idea.txt"},
        )
        saved = client.put(
            "/api/file-manager/files/text",
            json={
                "path": "notes/drafts/idea.txt",
                "content": "第一版内容\n",
                "revision": opened.json()["revision"],
            },
        )
        listing = client.get(
            "/api/file-manager/files",
            params={"path": "notes/drafts"},
        )
        renamed = client.patch(
            "/api/file-manager/files",
            json={
                "path": "notes/drafts/idea.txt",
                "name": "final.txt",
            },
        )
        downloaded = client.get(
            "/api/file-manager/files/download",
            params={"path": "notes/drafts/final.txt"},
        )
        archived = client.get(
            "/api/file-manager/files/download",
            params={"path": "notes"},
        )
        deleted = client.delete(
            "/api/file-manager/files",
            params={"path": "notes"},
        )

    assert scopes.status_code == 200
    assert scopes.json() == {
        "scopes": [
            "files",
            "skills",
            "python_templates",
        ]
    }
    assert empty.status_code == 200
    assert empty.json() == {"scope": "files", "path": "", "items": []}
    assert created_directory.status_code == 200
    assert created_file.status_code == 200
    assert opened.json()["content"] == ""
    assert saved.status_code == 200
    assert saved.json()["revision"] != opened.json()["revision"]
    assert [(item["name"], item["kind"]) for item in listing.json()["items"]] == [
        ("idea.txt", "file")
    ]
    assert renamed.status_code == 200
    assert renamed.json()["path"] == "notes/drafts/final.txt"
    assert downloaded.status_code == 200
    assert downloaded.content == "第一版内容\n".encode()
    assert 'filename="final.txt"' in downloaded.headers["content-disposition"]
    assert archived.status_code == 200
    assert archived.headers["content-type"] == "application/zip"
    assert 'filename="notes.zip"' in archived.headers["content-disposition"]
    with ZipFile(BytesIO(archived.content)) as archive:
        assert set(archive.namelist()) == {
            "notes/",
            "notes/drafts/",
            "notes/drafts/final.txt",
            "notes/empty/",
        }
        assert archive.read("notes/drafts/final.txt") == "第一版内容\n".encode()


def test_file_manager_uses_the_configured_text_editor_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        current = client.get("/api/system/runtime-policy").json()
        update = {
            key: value
            for key, value in current.items()
            if key not in {"defaults", "minimums", "configurable"}
        }
        update["text_edit_bytes"] = 4
        assert client.put("/api/system/runtime-policy", json=update).status_code == 200
        assert client.post(
            "/api/file-manager/files/text-files",
            json={"path": "small.txt"},
        ).status_code == 200
        opened = client.get(
            "/api/file-manager/files/text",
            params={"path": "small.txt"},
        )
        saved = client.put(
            "/api/file-manager/files/text",
            json={
                "path": "small.txt",
                "content": "12345",
                "revision": opened.json()["revision"],
            },
        )

    assert saved.status_code == 413
    assert saved.json()["detail"]["message_args"] == {"max_bytes": 4}


def test_file_upload_streams_nested_paths_and_requires_explicit_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        uploaded = client.put(
            "/api/file-manager/skills/upload",
            params={"path": "outline/references/example.md"},
            content=b"first",
            headers={"Content-Type": "application/octet-stream"},
        )
        conflict = client.put(
            "/api/file-manager/skills/upload",
            params={"path": "outline/references/example.md"},
            content=b"second",
        )
        replaced = client.put(
            "/api/file-manager/skills/upload",
            params={"path": "outline/references/example.md", "overwrite": "true"},
            content=b"second",
        )
        downloaded = client.get(
            "/api/file-manager/skills/download",
            params={"path": "outline/references/example.md"},
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["size"] == 5
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "file_already_exists"
    assert replaced.status_code == 200
    assert downloaded.content == b"second"


def test_rename_changes_only_the_entry_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        client.post(
            "/api/file-manager/files/text-files",
            json={"path": "note.txt"},
        )
        invalid = client.patch(
            "/api/file-manager/files",
            json={"path": "note.txt", "name": "folder/moved.txt"},
        )
        renamed = client.patch(
            "/api/file-manager/files",
            json={"path": "note.txt", "name": "renamed.txt"},
        )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "file_path_invalid"
    assert renamed.status_code == 200
    assert renamed.json()["path"] == "renamed.txt"
    assert not (tmp_path / "data" / "files" / "note.txt").exists()
    assert (tmp_path / "data" / "files" / "renamed.txt").is_file()


def test_archive_preview_and_download_support_mixed_multiple_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        client.put(
            "/api/file-manager/files/upload",
            params={"path": "readme.txt"},
            content=b"root",
        )
        client.put(
            "/api/file-manager/files/upload",
            params={"path": "documents/nested/note.txt"},
            content=b"nested",
        )
        client.post(
            "/api/file-manager/files/directories",
            json={"path": "documents/empty"},
        )
        client.post(
            "/api/file-manager/files/directories",
            json={"path": "images"},
        )
        selection = {
            "paths": ["readme.txt", "documents", "images", "documents"]
        }
        preview = client.post(
            "/api/file-manager/files/archive/preview",
            json=selection,
        )
        archived = client.post(
            "/api/file-manager/files/archive",
            json=selection,
        )

    assert preview.status_code == 200
    assert preview.json() == {
        "total_size": 10,
        "file_count": 2,
        "directory_count": 4,
    }
    assert archived.status_code == 200
    assert archived.headers["content-type"] == "application/zip"
    assert 'filename="agent-shell-files.zip"' in archived.headers["content-disposition"]
    with ZipFile(BytesIO(archived.content)) as archive:
        assert set(archive.namelist()) == {
            "readme.txt",
            "documents/",
            "documents/nested/",
            "documents/nested/note.txt",
            "documents/empty/",
            "images/",
        }
        assert archive.read("readme.txt") == b"root"
        assert archive.read("documents/nested/note.txt") == b"nested"
    assert not list((tmp_path / "runtime" / "tmp").glob("*.zip"))


def test_archive_requires_a_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        preview = client.post(
            "/api/file-manager/files/archive/preview",
            json={"paths": []},
        )
        archived = client.post(
            "/api/file-manager/files/archive",
            json={"paths": []},
        )

    assert preview.status_code == 422
    assert preview.json()["detail"]["code"] == "file_selection_required"
    assert archived.status_code == 422
    assert archived.json()["detail"]["code"] == "file_selection_required"


def test_text_save_detects_revision_conflicts_and_non_utf8_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        client.put(
            "/api/file-manager/files/upload",
            params={"path": "shared.txt"},
            content=b"original",
        )
        opened = client.get(
            "/api/file-manager/files/text", params={"path": "shared.txt"}
        ).json()
        (tmp_path / "data" / "files" / "shared.txt").write_text(
            "external change", encoding="utf-8"
        )
        conflict = client.put(
            "/api/file-manager/files/text",
            json={
                "path": "shared.txt",
                "content": "stale edit",
                "revision": opened["revision"],
            },
        )
        client.put(
            "/api/file-manager/files/upload",
            params={"path": "binary.bin"},
            content=b"\xff\xfe",
        )
        binary = client.get(
            "/api/file-manager/files/text", params={"path": "binary.bin"}
        )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "text_file_revision_conflict"
    assert (tmp_path / "data" / "files" / "shared.txt").read_text() == (
        "external change"
    )
    assert binary.status_code == 415
    assert binary.json()["detail"]["code"] == "text_file_invalid_encoding"


@pytest.mark.parametrize(
    "path",
    ["../outside.txt", "/absolute.txt", "nested\\escape.txt", "C:/drive.txt"],
)
def test_file_manager_rejects_paths_outside_the_selected_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        response = client.put(
            "/api/file-manager/files/upload",
            params={"path": path},
            content=b"blocked",
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "file_path_invalid"
    assert not (tmp_path / "outside.txt").exists()


def test_file_manager_exposes_only_user_scopes_and_rejects_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    link = tmp_path / "data" / "files" / "linked"
    archive_directory = tmp_path / "data" / "files" / "archive"
    nested_link = archive_directory / "linked"

    with make_client(tmp_path, monkeypatch) as client:
        hidden = client.get("/api/file-manager/config")
        archive_directory.mkdir()
        try:
            os.symlink(outside, link, target_is_directory=True)
            os.symlink(outside, nested_link, target_is_directory=True)
        except OSError:
            pytest.skip("This Windows account cannot create symbolic links.")
        linked = client.get(
            "/api/file-manager/files", params={"path": "linked"}
        )
        archived = client.post(
            "/api/file-manager/files/archive/preview",
            json={"paths": ["archive"]},
        )

    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "file_scope_not_found"
    assert linked.status_code == 422
    assert linked.json()["detail"]["code"] == "file_link_unsupported"
    assert archived.status_code == 422
    assert archived.json()["detail"]["code"] == "file_link_unsupported"
    assert outside_file.read_text(encoding="utf-8") == "secret"
