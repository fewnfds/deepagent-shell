from __future__ import annotations

from pathlib import Path

import pytest

from agent_shell.storage import atomic_files
from agent_shell.storage.atomic_files import write_bytes_atomic, write_text_atomic
from agent_shell.storage.owned_paths import (
    OwnedPathError,
    require_single_path_segment,
    resolve_owned_relative_path,
)


def test_atomic_file_replace_preserves_previous_content_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "nested" / "record.txt"
    write_text_atomic(path, "before\n")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(atomic_files.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        write_bytes_atomic(path, b"after\n")

    assert path.read_text(encoding="utf-8") == "before\n"
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "nested/name", "nested\\name", "C:relative"],
)
def test_single_path_segment_rejects_path_syntax(value: str) -> None:
    with pytest.raises(OwnedPathError):
        require_single_path_segment(value, label="owner")


def test_owned_relative_path_returns_normalized_path_inside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "owned"
    root.mkdir()

    path, normalized = resolve_owned_relative_path(root, "folder/main.py")

    assert path == root / "folder" / "main.py"
    assert normalized == "folder/main.py"


@pytest.mark.parametrize(
    "value",
    ["../outside", "folder/../outside", "/absolute", "folder\\main.py"],
)
def test_owned_relative_path_rejects_non_normalized_or_escaping_path(
    tmp_path: Path,
    value: str,
) -> None:
    with pytest.raises(OwnedPathError):
        resolve_owned_relative_path(tmp_path, value)
