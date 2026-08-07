from __future__ import annotations

import hashlib
import inspect
import mimetypes
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any


class ArtifactCommitError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


Reader = Callable[[str], bytes | Awaitable[bytes]]
Rule = Callable[[str, bytes], bool | str | Awaitable[bool | str]]
Transform = Callable[[str, str], str | Awaitable[str]]
Emitter = Callable[[dict[str, Any]], None | Awaitable[None]]


@dataclass(slots=True)
class ArtifactCommitter:
    reader: Reader
    emit: Emitter | None = None
    rule: Rule | None = None
    transform: Transform | None = None
    minimum_text_bytes: int = 1
    _committed: set[str] = field(default_factory=set)

    @staticmethod
    def canonical_path(path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise ArtifactCommitError("invalid_path", "commit path must be an absolute virtual path")
        normalized = str(PurePosixPath(path))
        if normalized != path or ".." in PurePosixPath(path).parts:
            raise ArtifactCommitError("invalid_path", "commit path must be canonical")
        return normalized

    async def commit(self, path: str) -> dict[str, Any]:
        canonical = self.canonical_path(path)
        if canonical in self._committed:
            raise ArtifactCommitError("already_committed", "the file was already committed in this lifecycle")
        try:
            value = self.reader(canonical)
            if inspect.isawaitable(value):
                value = await value
        except ArtifactCommitError:
            raise
        except Exception as exc:
            raise ArtifactCommitError("read_failed", "the file could not be read") from exc
        if not isinstance(value, bytes):
            raise ArtifactCommitError("read_failed", "the file reader returned an invalid value")

        self._committed.add(canonical)
        digest = hashlib.sha256(value).hexdigest()
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            event = {
                "event": "workflow.artifact.commit",
                "path": canonical,
                "status": "committed_metadata",
                "size": len(value),
                "media_type": mimetypes.guess_type(canonical)[0] or "application/octet-stream",
                "sha256": digest,
            }
            await self._emit(event)
            return {"status": "committed_metadata", "path": canonical}

        if len(value) < self.minimum_text_bytes:
            self._committed.remove(canonical)
            raise ArtifactCommitError("too_short", "the text file is shorter than the configured minimum")
        if self.rule is not None:
            result = self.rule(canonical, value)
            if inspect.isawaitable(result):
                result = await result
            if result is False:
                self._committed.remove(canonical)
                raise ArtifactCommitError("rejected", "the file was rejected by the commit rule")
            if isinstance(result, str):
                self._committed.remove(canonical)
                raise ArtifactCommitError("rejected", result)

        output = text
        if self.transform is not None:
            try:
                transformed = self.transform(canonical, text)
                if inspect.isawaitable(transformed):
                    transformed = await transformed
                if not isinstance(transformed, str):
                    raise TypeError("transform must return text")
                output = transformed
            except ArtifactCommitError:
                self._committed.remove(canonical)
                raise
            except Exception as exc:
                self._committed.remove(canonical)
                raise ArtifactCommitError("transform_failed", "the commit transform failed") from exc

        event = {
            "event": "workflow.artifact.commit",
            "path": canonical,
            "status": "committed",
            "content": output,
            "size": len(value),
            "sha256": digest,
            "media_type": mimetypes.guess_type(canonical)[0] or "text/plain",
        }
        await self._emit(event)
        return {"status": "committed", "path": canonical}

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.emit is None:
            return
        result = self.emit(event)
        if inspect.isawaitable(result):
            await result
