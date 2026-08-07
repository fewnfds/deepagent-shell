from __future__ import annotations

from .support import *

def test_state_files_can_be_created_overwritten_and_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.seen_messages = []
    ToolCallingFakeModel.bound_tool_names = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "write_file",
                    "args": {"file_path": "/draft.txt", "content": "first version"},
                    "id": "call-write-first",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "write_file",
                    "args": {"file_path": "/draft.txt", "content": "second version"},
                    "id": "call-write-second",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/draft.txt"},
                    "id": "call-read-overwrite",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "delete",
                    "args": {"file_path": "/draft.txt"},
                    "id": "call-delete-state",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "read_file",
                    "args": {"file_path": "/draft.txt"},
                    "id": "call-read-deleted",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="state filesystem completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Writable request files",
                "tool_configs": {"delete": {"visible": True}},
            },
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": replace_capability_reference(
                    main_agent, "filesystem", filesystem["id"]
                ),
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Update the draft."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == (
        "state filesystem completed"
    )
    assert "delete" in ToolCallingFakeModel.bound_tool_names
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[-1]
        if isinstance(message, ToolMessage)
    ]
    by_call_id = {message.tool_call_id: message for message in tool_results}
    assert "second version" in str(by_call_id["call-read-overwrite"].content)
    assert by_call_id["call-delete-state"].status == "success"
    assert by_call_id["call-read-deleted"].status == "error"

def test_mapped_directory_overwrite_and_recursive_delete_use_isolated_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapped = tmp_path / "mapped"
    nested = mapped / "obsolete"
    nested.mkdir(parents=True)
    target = mapped / "note.txt"
    target.write_text("old content", encoding="utf-8")
    (nested / "child.txt").write_text("remove me", encoding="utf-8")
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "write_file",
                    "args": {
                        "file_path": "/workspace/note.txt",
                        "content": "replacement content",
                    },
                    "id": "call-overwrite-mapped",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "delete",
                    "args": {"file_path": "/workspace/obsolete"},
                    "id": "call-delete-directory",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="mapped filesystem completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        main_agent = create_main_agent(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Mapped writable files",
                "mapped_directories": [{
                    "virtual_path": "/workspace/",
                    "local_path": str(mapped),
                }],
                "tool_configs": {"delete": {"visible": True}},
            },
        ).json()
        updated = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": main_agent["name"],
                "capability_refs": replace_capability_reference(
                    main_agent, "filesystem", filesystem["id"]
                ),
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": main_agent["name"],
                "messages": [{"role": "user", "content": "Clean the workspace."}],
            },
        )

    assert response.status_code == 200, response.text
    assert target.read_text(encoding="utf-8") == "replacement content"
    assert not nested.exists()
