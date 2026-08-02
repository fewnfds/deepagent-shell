from __future__ import annotations

from .support import *

def test_unselected_filesystem_exposes_no_filesystem_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ToolCallingFakeModel.bound_tool_names = []
    model = ToolCallingFakeModel(
        responses=[AIMessage(content="completed without filesystem")]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client, include_filesystem=False)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Answer directly."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == (
        "completed without filesystem"
    )
    assert ToolCallingFakeModel.bound_tool_names == []

def test_selected_filesystem_reads_request_initial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "seed" / "note.txt"
    source.parent.mkdir()
    source.write_text(
        "first line\nrequest-scoped file content\nthird line\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    ToolCallingFakeModel.bound_tool_names = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {
                            "file_path": "/input/note.txt",
                            "offset": 1,
                            "limit": 1,
                        },
                        "id": "call-read-file",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="filesystem completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Runtime filesystem",
                "virtual_files": [
                    {
                        "virtual_path": "/input/note.txt",
                        "source_path": str(source),
                    }
                ],
            },
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Read the file."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "filesystem completed"
    assert "read_file" in ToolCallingFakeModel.bound_tool_names
    assert "delete" not in ToolCallingFakeModel.bound_tool_names
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert len(tool_results) == 1
    assert "request-scoped file content" in str(tool_results[0].content)
    assert "lines 2-2 of 3 total" in str(tool_results[0].content)
    assert "1 line remaining from offset 2" in str(tool_results[0].content)

def test_empty_and_truncated_search_results_remain_opaque_tool_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deepagents.backends import StateBackend
    from deepagents.backends.protocol import GlobResult, GrepResult

    def glob_result(pattern: str) -> GlobResult:
        if pattern == "none":
            return GlobResult(error=None, matches=[], truncated=False)
        return GlobResult(
            error=None,
            matches=[{"path": "/partial.txt"}],
            truncated=True,
        )

    monkeypatch.setattr(
        StateBackend,
        "glob",
        lambda _self, pattern, path=None: glob_result(pattern),
    )

    async def fake_aglob(_self, pattern, path=None):
        return glob_result(pattern)

    monkeypatch.setattr(StateBackend, "aglob", fake_aglob)
    grep_result = GrepResult(
        error=None,
        matches=[{"path": "/partial.txt", "line": 1, "text": "needle"}],
        truncated=True,
    )
    monkeypatch.setattr(
        StateBackend,
        "grep",
        lambda _self, pattern, path=None, glob=None, *, max_count=None: grep_result,
    )

    async def fake_agrep(
        _self, pattern, path=None, glob=None, *, max_count=None
    ):
        return grep_result

    monkeypatch.setattr(StateBackend, "agrep", fake_agrep)
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "glob",
                    "args": {"pattern": "none"},
                    "id": "call-glob-empty",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "glob",
                    "args": {"pattern": "partial"},
                    "id": "call-glob-truncated",
                    "type": "tool_call",
                }],
            ),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "grep",
                    "args": {"pattern": "needle", "output_mode": "content"},
                    "id": "call-grep-truncated",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="search output completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Searchable files"},
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Search files."}],
            },
        )

    assert response.status_code == 200, response.text
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[-1]
        if isinstance(message, ToolMessage)
    ]
    by_call_id = {message.tool_call_id: message for message in tool_results}
    assert by_call_id["call-glob-empty"].content == "No files found"
    assert "partial.txt" in str(by_call_id["call-glob-truncated"].content)
    assert "paths above are valid but incomplete" in str(
        by_call_id["call-glob-truncated"].content
    )
    assert "needle" in str(by_call_id["call-grep-truncated"].content)
    assert "matches above are valid but incomplete" in str(
        by_call_id["call-grep-truncated"].content
    )

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
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={
                "name": "Writable request files",
                "tool_configs": {"delete": {"visible": True}},
            },
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
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
        primary = create_primary(client)
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Clean the workspace."}],
            },
        )

    assert response.status_code == 200, response.text
    assert target.read_text(encoding="utf-8") == "replacement content"
    assert not nested.exists()

def test_selected_skill_is_mounted_on_shared_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data" / "resources" / "skills" / "outline"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: outline\ndescription: Outline a document.\n---\n"
        "# Outline workflow\nUse three headings.\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    ToolCallingFakeModel.bound_tool_names = []
    model = ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/skills/outline/SKILL.md"},
                        "id": "call-read-skill",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="skill completed"),
        ]
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem", json={"name": "Skill filesystem"}
        ).json()
        skill = client.post(
            "/api/blocks/skill",
            json={"name": "Runtime skill", "skills": ["outline"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
                    ),
                    {"type": "skill", "block_id": skill["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Use the outline skill."}],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"] == "skill completed"
    system_messages = [
        message
        for message in ToolCallingFakeModel.seen_messages[0]
        if message.type == "system"
    ]
    assert any("outline" in message.text for message in system_messages)
    tool_results = [
        message
        for message in ToolCallingFakeModel.seen_messages[1]
        if isinstance(message, ToolMessage)
    ]
    assert len(tool_results) == 1
    assert "Use three headings" in str(tool_results[0].content)

def test_missing_selected_skill_fails_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "data" / "resources" / "skills" / "disappearing"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: disappearing\ndescription: Runtime validation.\n---\n",
        encoding="utf-8",
    )
    ToolCallingFakeModel.seen_messages = []
    model = ToolCallingFakeModel(responses=[AIMessage(content="must not run")])

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            lambda _block, _credential, _http_clients: model,
        )
        primary = create_primary(client)
        filesystem = client.post(
            "/api/blocks/filesystem", json={"name": "Missing Skill filesystem"}
        ).json()
        skill = client.post(
            "/api/blocks/skill",
            json={"name": "Missing runtime Skill", "skills": ["disappearing"]},
        ).json()
        updated = client.put(
            f"/api/primary-agents/{primary['id']}",
            json={
                "name": primary["name"],
                "capability_refs": [
                    *replace_capability_reference(
                        primary, "filesystem", filesystem["id"]
                    ),
                    {"type": "skill", "block_id": skill["id"]},
                ],
                "subagents": [],
            },
        )
        assert updated.status_code == 200, updated.text
        skill_file.unlink()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": primary["name"],
                "messages": [{"role": "user", "content": "Do not call provider."}],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "middleware_materialization_failed"
    assert str(skill_file) not in response.text
    assert ToolCallingFakeModel.seen_messages == []
