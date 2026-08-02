from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from agent_shell.api.errors import management_error
from agent_shell.file_manager import FileManagerError, FileManagerService


class FilePathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)


class FileRenameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)
    name: str = Field(max_length=255)


class FileSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str]


class TextFileSaveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(max_length=4096)
    content: str
    revision: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


def _raise_file_error(error: FileManagerError) -> NoReturn:
    raise management_error(
        error.status_code,
        code=error.code,
        message_key=error.message_key,
        message=str(error),
        message_args=error.message_args,
    ) from error


def build_file_manager_router(files: FileManagerService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/file-manager")
    async def list_scopes() -> dict:
        return files.list_scopes()

    @router.get("/api/file-manager/{scope}")
    async def list_directory(
        scope: str,
        path: str = Query(default="", max_length=4096),
    ) -> dict:
        try:
            return files.list_directory(scope, path)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.post("/api/file-manager/{scope}/directories")
    async def create_directory(scope: str, payload: FilePathInput) -> dict:
        try:
            return files.create_directory(scope, payload.path)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.post("/api/file-manager/{scope}/text-files")
    async def create_text_file(scope: str, payload: FilePathInput) -> dict:
        try:
            return files.create_text_file(scope, payload.path)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.put("/api/file-manager/{scope}/upload")
    async def upload_file(
        scope: str,
        request: Request,
        path: str = Query(max_length=4096),
        overwrite: bool = Query(default=False),
    ) -> dict:
        try:
            return await files.upload(
                scope,
                path,
                request.stream(),
                overwrite=overwrite,
            )
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.get("/api/file-manager/{scope}/download")
    async def download_file(
        scope: str,
        path: str = Query(max_length=4096),
    ) -> FileResponse:
        try:
            download = files.prepare_download(scope, path)
        except FileManagerError as exc:
            _raise_file_error(exc)
        return FileResponse(
            download.path,
            filename=download.filename,
            media_type=download.media_type,
            background=(
                BackgroundTask(download.path.unlink, missing_ok=True)
                if download.delete_after
                else None
            ),
        )

    @router.post("/api/file-manager/{scope}/archive/preview")
    async def preview_archive(scope: str, payload: FileSelectionInput) -> dict:
        try:
            return files.preview_archive(scope, payload.paths)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.post("/api/file-manager/{scope}/archive")
    async def download_archive(
        scope: str,
        payload: FileSelectionInput,
    ) -> FileResponse:
        try:
            download = files.prepare_archive(scope, payload.paths)
        except FileManagerError as exc:
            _raise_file_error(exc)
        return FileResponse(
            download.path,
            filename=download.filename,
            media_type=download.media_type,
            background=BackgroundTask(download.path.unlink, missing_ok=True),
        )

    @router.get("/api/file-manager/{scope}/text")
    async def read_text_file(
        scope: str,
        path: str = Query(max_length=4096),
    ) -> dict:
        try:
            return files.read_text(scope, path)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.put("/api/file-manager/{scope}/text")
    async def save_text_file(scope: str, payload: TextFileSaveInput) -> dict:
        try:
            return files.save_text(
                scope,
                payload.path,
                payload.content,
                payload.revision,
            )
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.patch("/api/file-manager/{scope}")
    async def rename_file(scope: str, payload: FileRenameInput) -> dict:
        try:
            return files.rename(scope, payload.path, payload.name)
        except FileManagerError as exc:
            _raise_file_error(exc)

    @router.delete("/api/file-manager/{scope}")
    async def delete_file(
        scope: str,
        path: str = Query(max_length=4096),
    ) -> dict:
        try:
            return files.delete(scope, path)
        except FileManagerError as exc:
            _raise_file_error(exc)

    return router
