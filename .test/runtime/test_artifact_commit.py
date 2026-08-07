from __future__ import annotations

import asyncio

import pytest

from agent_shell.workflow.artifacts import ArtifactCommitError, ArtifactCommitter


def test_commit_streams_transformed_utf8_text_once() -> None:
    events: list[dict] = []

    async def run() -> None:
        committer = ArtifactCommitter(
            reader=lambda _path: b"report",
            emit=events.append,
            transform=lambda _path, text: f"<tag>{text}</tag>",
        )
        assert await committer.commit("/output/report.md") == {
            "status": "committed",
            "path": "/output/report.md",
        }
        with pytest.raises(ArtifactCommitError, match="already committed"):
            await committer.commit("/output/report.md")

    asyncio.run(run())
    assert events[0]["content"] == "<tag>report</tag>"


def test_binary_commit_streams_metadata_only() -> None:
    events: list[dict] = []

    async def run() -> None:
        await ArtifactCommitter(
            reader=lambda _path: b"\xff\x00",
            emit=events.append,
        ).commit("/output/archive.bin")

    asyncio.run(run())
    assert events[0]["status"] == "committed_metadata"
    assert "content" not in events[0]
