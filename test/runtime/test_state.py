from __future__ import annotations

from agent_shell.runtime.state import AgentShellState, merge_shared_vars


def test_shared_vars_reducer_merges_independent_patches() -> None:
    assert merge_shared_vars(
        {"research": {"status": "ready"}},
        {"report": {"path": "/report.md"}},
    ) == {
        "research": {"status": "ready"},
        "report": {"path": "/report.md"},
    }


def test_agent_shell_state_exposes_shared_vars_as_public_graph_state() -> None:
    assert "shared_vars" in AgentShellState.__annotations__
