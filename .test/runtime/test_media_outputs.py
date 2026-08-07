from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import sqlite3
import threading

import pytest

from agent_shell.runtime.media_response import MainAgentMediaResponse
from agent_shell.runtime.output_stream import MainAgentMediaBlock
from agent_shell.storage.database import SQLiteDatabase
from agent_shell.storage.media_outputs import MediaOutputStore, MediaProjection


_PRE_OUTPUT_SCHEMA = """
CREATE TABLE api_message_history (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    request_body TEXT NOT NULL,
    response_body TEXT,
    response_content_type TEXT,
    http_status INTEGER,
    error_code TEXT
);

CREATE TABLE agent_session_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    input_messages_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    response_text TEXT NOT NULL
);
"""


def test_media_store_starts_with_existing_history_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "state" / "agent-shell.sqlite3"
    database_path.parent.mkdir(parents=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(_PRE_OUTPUT_SCHEMA)

    database = SQLiteDatabase(database_path)
    MediaOutputStore(database, tmp_path / "data" / "media" / "outputs")

    with database.transaction() as connection:
        output_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "api_message_history_outputs",
        "agent_session_run_outputs",
    }.issubset(output_tables)


def test_failed_file_cleanup_keeps_asset_index_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = SQLiteDatabase(tmp_path / "data" / "state" / "agent-shell.sqlite3")
    store = MediaOutputStore(database, tmp_path / "data" / "media" / "outputs")
    projection = store.persist(
        request_id="request-1",
        message_id="message-1",
        block_index=0,
        block={
            "type": "image",
            "mime_type": "image/png",
            "base64": base64.b64encode(b"image").decode("ascii"),
        },
    )
    assert projection.asset is not None
    asset_id = str(projection.asset["id"])
    target = tmp_path / str(projection.asset["relative_path"])
    original_unlink = Path.unlink

    def fail_target_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path.resolve() == target.resolve():
            raise PermissionError("test cleanup failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_target_unlink)
    store.finish_request("request-1")

    with database.transaction() as connection:
        retained = connection.execute(
            "SELECT id FROM media_output_assets WHERE id = ?", (asset_id,)
        ).fetchone()
    assert retained is not None
    assert target.exists()

    monkeypatch.setattr(Path, "unlink", original_unlink)
    store.cleanup_unreferenced()

    with database.transaction() as connection:
        removed = connection.execute(
            "SELECT id FROM media_output_assets WHERE id = ?", (asset_id,)
        ).fetchone()
    assert removed is None
    assert not target.exists()


def test_cancelled_projection_waits_for_persistence_without_publishing() -> None:
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class BlockingStore:
        def persist(self, **_kwargs: object) -> MediaProjection:
            started.set()
            release.wait(timeout=2)
            finished.set()
            return MediaProjection(
                notification="saved",
                structured_block={"type": "image"},
                asset={"id": "asset-1"},
            )

    async def run() -> None:
        response = MainAgentMediaResponse(BlockingStore(), "request-1")  # type: ignore[arg-type]
        task = asyncio.create_task(
            response.project(
                MainAgentMediaBlock(
                    timestamp="2026-01-01T00:00:00+00:00",
                    namespace="main_agent",
                    agent_name="main_agent",
                    node="model",
                    message_id="message-1",
                    block_index=0,
                    content={"type": "image"},
                )
            )
        )
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert response.assets == []

    asyncio.run(run())
