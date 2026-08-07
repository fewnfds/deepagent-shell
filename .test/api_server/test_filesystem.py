from __future__ import annotations

from .support import *
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
        main_agent = create_main_agent(client)
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
        main_agent = create_main_agent(client)
        filesystem = client.post(
            "/api/blocks/filesystem",
            json={"name": "Searchable files"},
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
