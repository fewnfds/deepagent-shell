from __future__ import annotations

from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from agent_shell.storage.runtime_policy import RUNTIME_POLICY_DEFAULTS, RuntimePolicyStore

RELATIVE_PATH_MAX_LENGTH = 4096
_TEMPORARY_PREFIX = ".agent-shell-write-"
_WINDOWS_INVALID_CHARACTERS = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class FileDownload:
    path: Path
    filename: str
    media_type: str
    delete_after: bool = False


class FileManagerError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message_key: str,
        fallback: str,
        message_args: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        self.message_args = message_args or {}
        super().__init__(fallback)


class FileManagerService:
    def __init__(
        self,
        scopes: dict[str, Path],
        temporary_directory: Path,
        runtime_policy: RuntimePolicyStore | None = None,
    ) -> None:
        self._scopes = {name: path.resolve() for name, path in scopes.items()}
        self._temporary_directory = temporary_directory.resolve()
        self._runtime_policy = runtime_policy

    def _text_edit_max_bytes(self) -> int:
        return (
            self._runtime_policy.snapshot().text_edit_bytes
            if self._runtime_policy is not None
            else RUNTIME_POLICY_DEFAULTS.text_edit_bytes
        )

    def list_scopes(self) -> dict[str, list[str]]:
        return {"scopes": list(self._scopes)}

    def _scope_root(self, scope: str) -> Path:
        root = self._scopes.get(scope)
        if root is None:
            raise FileManagerError(
                404,
                "file_scope_not_found",
                "errors.fileScopeNotFound",
                "The file scope does not exist.",
            )
        return root

    @staticmethod
    def _validate_segment(segment: str) -> None:
        invalid = (
            not segment
            or len(segment) > 255
            or segment in {".", ".."}
            or segment.startswith(_TEMPORARY_PREFIX)
            or segment.endswith((" ", "."))
            or any(ord(character) < 32 for character in segment)
            or any(character in _WINDOWS_INVALID_CHARACTERS for character in segment)
            or segment.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        )
        if invalid:
            raise FileManagerError(
                422,
                "file_path_invalid",
                "errors.filePathInvalid",
                "The relative file path is invalid.",
            )

    @staticmethod
    def _is_reparse_point(path: Path) -> bool:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)

    def _path(
        self,
        scope: str,
        relative_path: str,
        *,
        allow_root: bool = False,
    ) -> tuple[Path, str]:
        root = self._scope_root(scope)
        if not isinstance(relative_path, str) or len(relative_path) > RELATIVE_PATH_MAX_LENGTH:
            raise FileManagerError(
                422,
                "file_path_invalid",
                "errors.filePathInvalid",
                "The relative file path is invalid.",
            )
        if relative_path == "":
            if allow_root:
                return root, ""
            raise FileManagerError(
                422,
                "file_path_required",
                "errors.filePathRequired",
                "A relative file path is required.",
            )
        if "\\" in relative_path:
            raise FileManagerError(
                422,
                "file_path_invalid",
                "errors.filePathInvalid",
                "The relative file path is invalid.",
            )
        pure = PurePosixPath(relative_path)
        parts = pure.parts
        if pure.is_absolute() or not parts or relative_path != "/".join(parts):
            raise FileManagerError(
                422,
                "file_path_invalid",
                "errors.filePathInvalid",
                "The relative file path is invalid.",
            )
        for segment in parts:
            self._validate_segment(segment)

        current = root
        for segment in parts:
            current = current / segment
            if current.exists() or os.path.lexists(current):
                if self._is_reparse_point(current):
                    raise FileManagerError(
                        422,
                        "file_link_unsupported",
                        "errors.fileLinkUnsupported",
                        "Symbolic links and reparse points are not supported.",
                    )
        return current, "/".join(parts)

    @staticmethod
    def _modified_at(timestamp: float) -> str:
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )

    @staticmethod
    def _metadata_revision(metadata: os.stat_result) -> str:
        return f"{metadata.st_mtime_ns:x}-{metadata.st_size:x}"

    @staticmethod
    def _content_revision(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _missing() -> FileManagerError:
        return FileManagerError(
            404,
            "file_not_found",
            "errors.fileNotFound",
            "The file or directory does not exist.",
        )

    @staticmethod
    def _operation_failed() -> FileManagerError:
        return FileManagerError(
            409,
            "file_operation_failed",
            "errors.fileOperationFailed",
            "The file operation could not be completed.",
        )

    def list_directory(self, scope: str, relative_path: str = "") -> dict[str, Any]:
        directory, normalized = self._path(scope, relative_path, allow_root=True)
        if not directory.exists():
            raise self._missing()
        if not directory.is_dir():
            raise FileManagerError(
                409,
                "file_not_directory",
                "errors.fileNotDirectory",
                "The selected path is not a directory.",
            )
        items: list[dict[str, Any]] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name.startswith(_TEMPORARY_PREFIX):
                        continue
                    metadata = entry.stat(follow_symlinks=False)
                    attributes = getattr(metadata, "st_file_attributes", 0)
                    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                    unsupported = entry.is_symlink() or bool(attributes & reparse_flag)
                    kind = (
                        "unsupported"
                        if unsupported
                        else "directory"
                        if entry.is_dir(follow_symlinks=False)
                        else "file"
                        if entry.is_file(follow_symlinks=False)
                        else "unsupported"
                    )
                    item_path = f"{normalized}/{entry.name}" if normalized else entry.name
                    items.append(
                        {
                            "name": entry.name,
                            "path": item_path,
                            "kind": kind,
                            "size": metadata.st_size if kind == "file" else None,
                            "modified_at": self._modified_at(metadata.st_mtime),
                            "revision": self._metadata_revision(metadata),
                        }
                    )
        except OSError as exc:
            raise self._operation_failed() from exc
        items.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold()))
        return {"scope": scope, "path": normalized, "items": items}

    def create_directory(self, scope: str, relative_path: str) -> dict[str, Any]:
        target, normalized = self._path(scope, relative_path)
        try:
            target.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise FileManagerError(
                409,
                "file_already_exists",
                "errors.fileAlreadyExists",
                "A file or directory already exists at the destination.",
            ) from exc
        except OSError as exc:
            raise self._operation_failed() from exc
        return {"scope": scope, "path": normalized, "kind": "directory"}

    def create_text_file(self, scope: str, relative_path: str) -> dict[str, Any]:
        target, normalized = self._path(scope, relative_path)
        if not target.parent.is_dir():
            raise self._missing()
        try:
            with target.open("x", encoding="utf-8", newline=""):
                pass
        except FileExistsError as exc:
            raise FileManagerError(
                409,
                "file_already_exists",
                "errors.fileAlreadyExists",
                "A file or directory already exists at the destination.",
            ) from exc
        except OSError as exc:
            raise self._operation_failed() from exc
        return {
            "scope": scope,
            "path": normalized,
            "kind": "file",
            "revision": self._content_revision(b""),
        }

    async def upload(
        self,
        scope: str,
        relative_path: str,
        chunks: AsyncIterable[bytes],
        *,
        overwrite: bool,
    ) -> dict[str, Any]:
        target, normalized = self._path(scope, relative_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise self._operation_failed() from exc
        self._path(scope, "/".join(PurePosixPath(normalized).parts[:-1]), allow_root=True)
        if target.exists() and not overwrite:
            raise FileManagerError(
                409,
                "file_already_exists",
                "errors.fileAlreadyExists",
                "A file or directory already exists at the destination.",
            )
        if target.exists() and not target.is_file():
            raise FileManagerError(
                409,
                "file_not_regular",
                "errors.fileNotRegular",
                "The selected path is not a regular file.",
            )

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=_TEMPORARY_PREFIX,
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        size = 0
        try:
            with os.fdopen(descriptor, "wb") as output:
                async for chunk in chunks:
                    output.write(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise self._operation_failed() from exc
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return {"scope": scope, "path": normalized, "kind": "file", "size": size}

    def _download_path(self, scope: str, relative_path: str) -> Path:
        target, _ = self._path(scope, relative_path)
        if not target.exists():
            raise self._missing()
        if not target.is_file() and not target.is_dir():
            raise FileManagerError(
                409,
                "file_not_regular",
                "errors.fileNotRegular",
                "The selected path is not a regular file or directory.",
            )
        return target

    def _archive_targets(self, scope: str, relative_paths: list[str]) -> list[Path]:
        if not relative_paths:
            raise FileManagerError(
                422,
                "file_selection_required",
                "errors.fileSelectionRequired",
                "Select at least one file or directory.",
            )
        targets: list[Path] = []
        selected_paths: set[Path] = set()
        archive_names: set[str] = set()
        for relative_path in relative_paths:
            target = self._download_path(scope, relative_path)
            if target in selected_paths:
                continue
            if target.name in archive_names:
                raise FileManagerError(
                    422,
                    "file_archive_name_conflict",
                    "errors.fileArchiveNameConflict",
                    "Selected entries must have unique names.",
                )
            selected_paths.add(target)
            archive_names.add(target.name)
            targets.append(target)
        return targets

    def _archive_entries(
        self,
        target: Path,
    ) -> Iterator[tuple[Path, str, bool, int]]:
        if target.is_file():
            try:
                metadata = target.stat()
            except OSError as exc:
                raise self._operation_failed() from exc
            yield target, target.name, False, metadata.st_size
            return

        yield target, f"{target.name}/", True, 0
        pending = [target]
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as scanned:
                    entries = sorted(scanned, key=lambda item: item.name.casefold())
            except OSError as exc:
                raise self._operation_failed() from exc
            child_directories: list[Path] = []
            for entry in entries:
                if entry.name.startswith(_TEMPORARY_PREFIX):
                    continue
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise self._operation_failed() from exc
                attributes = getattr(metadata, "st_file_attributes", 0)
                reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                if entry.is_symlink() or bool(attributes & reparse_flag):
                    raise FileManagerError(
                        422,
                        "file_link_unsupported",
                        "errors.fileLinkUnsupported",
                        "Symbolic links and reparse points are not supported.",
                    )
                path = Path(entry.path)
                archive_path = (
                    Path(target.name) / path.relative_to(target)
                ).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    yield path, f"{archive_path}/", True, 0
                    child_directories.append(path)
                elif entry.is_file(follow_symlinks=False):
                    yield path, archive_path, False, metadata.st_size
                else:
                    raise FileManagerError(
                        409,
                        "file_not_regular",
                        "errors.fileNotRegular",
                        "The selected path is not a regular file or directory.",
                    )
            pending.extend(reversed(child_directories))

    def preview_archive(self, scope: str, relative_paths: list[str]) -> dict[str, int]:
        targets = self._archive_targets(scope, relative_paths)
        total_size = 0
        file_count = 0
        directory_count = 0
        for target in targets:
            for _, _, is_directory, size in self._archive_entries(target):
                if is_directory:
                    directory_count += 1
                else:
                    file_count += 1
                    total_size += size
        return {
            "total_size": total_size,
            "file_count": file_count,
            "directory_count": directory_count,
        }

    def prepare_archive(self, scope: str, relative_paths: list[str]) -> FileDownload:
        targets = self._archive_targets(scope, relative_paths)
        try:
            self._temporary_directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=_TEMPORARY_PREFIX,
                suffix=".zip",
                dir=self._temporary_directory,
            )
        except OSError as exc:
            raise self._operation_failed() from exc
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with ZipFile(
                temporary,
                mode="w",
                compression=ZIP_DEFLATED,
                allowZip64=True,
            ) as archive:
                for target in targets:
                    for path, archive_path, is_directory, _ in self._archive_entries(target):
                        if is_directory:
                            archive.writestr(archive_path, b"")
                        else:
                            archive.write(path, archive_path)
        except FileManagerError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise self._operation_failed() from exc
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return FileDownload(
            path=temporary,
            filename=(
                f"{targets[0].name}.zip"
                if len(targets) == 1
                else "agent-shell-files.zip"
            ),
            media_type="application/zip",
            delete_after=True,
        )

    def prepare_download(self, scope: str, relative_path: str) -> FileDownload:
        target = self._download_path(scope, relative_path)
        if target.is_dir():
            return self.prepare_archive(scope, [relative_path])
        return FileDownload(
            path=target,
            filename=target.name,
            media_type="application/octet-stream",
        )

    def _regular_file_path(self, scope: str, relative_path: str) -> Path:
        target = self._download_path(scope, relative_path)
        if not target.is_file():
            raise FileManagerError(
                409,
                "file_not_regular",
                "errors.fileNotRegular",
                "The selected path is not a regular file.",
            )
        return target

    def read_text(self, scope: str, relative_path: str) -> dict[str, Any]:
        target = self._regular_file_path(scope, relative_path)
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise self._operation_failed() from exc
        max_bytes = self._text_edit_max_bytes()
        if len(content) > max_bytes:
            raise FileManagerError(
                413,
                "text_file_too_large",
                "errors.textFileTooLarge",
                "The file is too large for the text editor.",
                {"max_bytes": max_bytes},
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileManagerError(
                415,
                "text_file_invalid_encoding",
                "errors.textFileInvalidEncoding",
                "The text editor supports UTF-8 files only.",
            ) from exc
        return {
            "scope": scope,
            "path": relative_path,
            "content": text,
            "revision": self._content_revision(content),
        }

    def save_text(
        self,
        scope: str,
        relative_path: str,
        content: str,
        revision: str,
    ) -> dict[str, Any]:
        target = self._regular_file_path(scope, relative_path)
        try:
            current = target.read_bytes()
        except OSError as exc:
            raise self._operation_failed() from exc
        if self._content_revision(current) != revision:
            raise FileManagerError(
                409,
                "text_file_revision_conflict",
                "errors.textFileRevisionConflict",
                "The file changed after it was opened.",
            )
        encoded = content.encode("utf-8")
        max_bytes = self._text_edit_max_bytes()
        if len(encoded) > max_bytes:
            raise FileManagerError(
                413,
                "text_file_too_large",
                "errors.textFileTooLarge",
                "The file is too large for the text editor.",
                {"max_bytes": max_bytes},
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=_TEMPORARY_PREFIX,
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise self._operation_failed() from exc
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return {
            "scope": scope,
            "path": relative_path,
            "revision": self._content_revision(encoded),
        }

    def rename(self, scope: str, relative_path: str, name: str) -> dict[str, Any]:
        self._validate_segment(name)
        source, source_normalized = self._path(scope, relative_path)
        if not source.exists():
            raise self._missing()
        parent_path = PurePosixPath(source_normalized).parent
        destination_normalized = (
            name if parent_path == PurePosixPath(".") else f"{parent_path.as_posix()}/{name}"
        )
        destination, destination_normalized = self._path(scope, destination_normalized)
        if destination == source:
            return {
                "scope": scope,
                "source_path": source_normalized,
                "path": source_normalized,
            }
        if destination.exists() or os.path.lexists(destination):
            raise FileManagerError(
                409,
                "file_already_exists",
                "errors.fileAlreadyExists",
                "A file or directory already exists at the destination.",
            )
        try:
            os.replace(source, destination)
        except OSError as exc:
            raise self._operation_failed() from exc
        return {
            "scope": scope,
            "source_path": source_normalized,
            "path": destination_normalized,
        }

    def delete(self, scope: str, relative_path: str) -> dict[str, Any]:
        target, normalized = self._path(scope, relative_path)
        if not target.exists():
            raise self._missing()
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.is_file():
                target.unlink()
            else:
                raise FileManagerError(
                    409,
                    "file_not_regular",
                    "errors.fileNotRegular",
                    "The selected path is not a regular file or directory.",
                )
        except FileManagerError:
            raise
        except OSError as exc:
            raise self._operation_failed() from exc
        return {"scope": scope, "path": normalized, "deleted": True}
