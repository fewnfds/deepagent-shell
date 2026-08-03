from __future__ import annotations

from .support import *
from agent_shell.runtime.capabilities import deepagents as deepagents_capability


def test_subagent_shares_primary_request_files_without_reloading_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "seed" / "note.txt"
    source.parent.mkdir()
    source.write_text("shared source content", encoding="utf-8")
    source_reads: list[Path] = []
    original_file_data_from_path = deepagents_capability._file_data_from_path

    def tracked_file_data_from_path(path: Path, create_file_data):
        if path == source:
            source_reads.append(path)
        return original_file_data_from_path(path, create_file_data)

    monkeypatch.setattr(
        deepagents_capability, "_file_data_from_path", tracked_file_data_from_path
    )

    class ParentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    class ChildModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        bound_tool_names: ClassVar[list[str]] = []
        bound_tool_descriptions: ClassVar[dict[str, str]] = {}

    parent_model = ParentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Read the shared source and create a draft.",
                            "subagent_type": "workspace_worker",
                        },
                        "id": "call-shared-worker",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/temp/child.txt"},
                        "id": "call-read-child-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="shared workspace completed"),
        ]
    )
    child_model = ChildModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/input/note.txt"},
                        "id": "call-child-read-source",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/temp/child.txt",
                            "content": "created by child",
                        },
                        "id": "call-child-write",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="child workspace updated"),
        ]
    )
    models = iter([parent_model, child_model])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, *_args: next(models),
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Shared request workspace",
                "virtual_files": [
                    {
                        "virtual_path": "/input/note.txt",
                        "source_path": str(source),
                    }
                ],
            },
        ).json()
        delegation = client.post(
            "/api/blocks/subagent",
            json={"name": "Shared workspace delegation"},
        ).json()
        subagent = client.post(
            "/api/subagents",
            json=subagent_payload(
                "Workspace worker",
                name="workspace_worker",
                description="Uses the current Primary workspace.",
            ),
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
                    ),
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": subagent["id"]}],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Use the shared workspace."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "shared workspace completed"
    )
    assert source_reads == [source]
    child_read_result = next(
        message
        for message in ChildModel.seen_messages[1]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "shared source content" in str(child_read_result.content)
    parent_read_result = next(
        message
        for message in ParentModel.seen_messages[2]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "created by child" in str(parent_read_result.content)


def test_new_request_resets_state_backend_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/temp/generated.txt",
                            "content": "first request only",
                        },
                        "id": "call-write-request-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="first request completed"),
        ]
    )
    reader = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/temp/generated.txt"},
                        "id": "call-read-request-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="second request completed"),
        ]
    )
    models = iter([writer, reader])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: next(models),
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Ephemeral request workspace"},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": replace_capability_reference(
                    primary, "filesystem", filesystem["id"]
                ),
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        first = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Create a temporary file."}],
            },
        )
        second = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Read the temporary file."}],
            },
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    read_result = next(
        message
        for message in ToolCallingFakeModel.seen_messages[-1]
        if isinstance(message, ToolMessage) and message.name == "read_file"
    )
    assert "not found" in str(read_result.content).lower()
