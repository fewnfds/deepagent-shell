from __future__ import annotations

from agent_shell.runtime.state import (
    AgentShellState,
    merge_agent_invocations,
    merge_shared_vars,
)


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


def test_agent_invocation_reducer_merges_independent_invocation_ids() -> None:
    first = {"first": {"invocation_id": "first"}}
    second = {"second": {"invocation_id": "second"}}

    assert merge_agent_invocations(first, second) == {**first, **second}
