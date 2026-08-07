from __future__ import annotations

import base64
import json

from langchain_core.messages import AIMessage

from .support import *


_MEDIA_BYTES = b"\x89PNG\r\n\x1a\nagent-shell-media-output"
_MEDIA_CASES = (
    ("image", "image/png", b"image-output"),
    ("audio", "audio/mpeg", b"audio-output"),
    ("video", "video/mp4", b"video-output"),
    ("file", "application/pdf", b"file-output"),
)


def _install_media_model(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = base64.b64encode(_MEDIA_BYTES).decode("ascii")
    monkeypatch.setattr(
        "agent_shell.runtime.agent_builder._build_chat_model",
        lambda _block, _credential, _http_clients: ToolCallingFakeModel(
            responses=[
                AIMessage(
                    content=[
                        {"type": "text", "text": "before "},
                        {
                            "type": "image",
                            "base64": encoded,
                            "mime_type": "image/png",
                        },
                        {"type": "text", "text": " after"},
                    ]
                )
            ]
        ),
    )


def test_main_agent_media_output_is_private_structured_and_reference_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        _install_media_model(monkeypatch)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "make an image"}],
            },
        )

        assert response.status_code == 200, response.text
        request_id = response.headers["x-request-id"]
        session_id = response.headers["x-agent-session-id"]
        content = response.json()["choices"][0]["message"]["content"]
        notification = "AI发送来了【图片】，已保存到【data/media/outputs/"
        assert content.startswith("before " + notification)
        assert content.endswith(" after")
        assert content.count(notification) == 1

        detail = client.get(f"/api/agent-sessions/{session_id}").json()
        run = detail["runs"][0]
        assert [block["type"] for block in run["response_blocks"]] == [
            "text",
            "image",
            "text",
        ]
        assert len(run["media_assets"]) == 1
        asset = run["media_assets"][0]
        assert asset["relative_path"].startswith("data/media/outputs/")
        asset_path = tmp_path / asset["relative_path"]
        assert asset_path.read_bytes() == _MEDIA_BYTES

        output = client.get(
            f"/api/agent-sessions/{session_id}/runs/{run['id']}/steps/output"
        ).json()["data"]
        history = client.get(
            "/api/event-feed",
            params=event_feed_params(source="api_call", query=request_id),
        ).json()["items"][0]
        history_entry = client.get(
            f"/api/event-feed/api_call/{history['id']}/download"
        ).json()["entry"]
        serialized = json.dumps(
            {"output": output, "history": history_entry}, ensure_ascii=False
        )
        assert output["response_blocks"] == run["response_blocks"]
        assert output["media_assets"] == run["media_assets"]
        assert history_entry["response_blocks"] == run["response_blocks"]
        assert history_entry["media_assets"] == run["media_assets"]
        assert base64.b64encode(_MEDIA_BYTES).decode("ascii") not in serialized
        assert str(tmp_path) not in serialized
        assert "http://" not in serialized and "https://" not in serialized

    with make_client(tmp_path, monkeypatch) as restarted:
        assert asset_path.read_bytes() == _MEDIA_BYTES
        assert restarted.delete(f"/api/agent-sessions/{session_id}").status_code == 200
        assert asset_path.exists()
        deleted = restarted.post(
            "/api/event-feed/delete",
            json={
                **EVENT_FEED_TEST_WINDOW,
                "source": ["api_call"],
                "level": [],
                "query": request_id,
            },
        )
        assert deleted.status_code == 200, deleted.text
        assert not asset_path.exists()


def test_streaming_main_agent_media_emits_one_notification_after_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        _install_media_model(monkeypatch)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "stream an image"}],
                "stream": True,
            },
        )

        assert response.status_code == 200, response.text
        content = streamed_content(response)
        notification = "AI发送来了【图片】，已保存到【data/media/outputs/"
        assert content.startswith("before " + notification)
        assert content.endswith(" after")
        assert content.count(notification) == 1
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()
        asset = session["runs"][0]["media_assets"][0]
        assert (tmp_path / asset["relative_path"]).read_bytes() == _MEDIA_BYTES


def test_remote_main_agent_media_reports_unsaved_without_persisting_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: ToolCallingFakeModel(
                responses=[
                    AIMessage(
                        content=[
                            {"type": "text", "text": "before "},
                            {
                                "type": "image",
                                "url": "https://private.example/image.png",
                            },
                        ]
                    )
                ]
            ),
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "return remote image"}],
            },
        )
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 200, response.text
    content = response.json()["choices"][0]["message"]["content"]
    assert content == "before AI发送来了【图片】，但返回内容无法保存。"
    run = session["runs"][0]
    assert run["media_assets"] == []
    assert run["response_blocks"][1] == {
        "type": "image",
        "saved": False,
        "reason": "source_unavailable",
        "source_type": "url",
    }
    assert "private.example" not in json.dumps(run, ensure_ascii=False)


def test_main_agent_output_materializes_image_audio_video_and_file_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocks: list[dict[str, str]] = []
    for media_type, mime_type, value in _MEDIA_CASES:
        blocks.extend(
            (
                {"type": "text", "text": f"<{media_type}>"},
                {
                    "type": media_type,
                    "base64": base64.b64encode(value).decode("ascii"),
                    "mime_type": mime_type,
                },
            )
        )
    with make_client(tmp_path, monkeypatch) as client:
        main_agent = create_main_agent(client)
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: ToolCallingFakeModel(
                responses=[AIMessage(content=blocks)]
            ),
        )
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "all media"}],
            },
        )
        session = client.get(
            f"/api/agent-sessions/{response.headers['x-agent-session-id']}"
        ).json()

    assert response.status_code == 200, response.text
    content = response.json()["choices"][0]["message"]["content"]
    labels = ("图片", "音频", "视频", "文件")
    positions = [content.index(f"AI发送来了【{label}】") for label in labels]
    assert positions == sorted(positions)
    assets = session["runs"][0]["media_assets"]
    assert [item["type"] for item in assets] == [
        media_type for media_type, _mime, _value in _MEDIA_CASES
    ]
    expected = {
        mime_type: value for _media_type, mime_type, value in _MEDIA_CASES
    }
    assert {
        item["mime_type"]: (tmp_path / item["relative_path"]).read_bytes()
        for item in assets
    } == expected
