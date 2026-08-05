from __future__ import annotations

from types import SimpleNamespace

from agent_shell.runtime import subagent_graphs
from agent_shell.runtime.subagent_graphs import SubagentGraphCompiler
from agent_shell.validation.service import ResolvedSubagent, ResolvedSubagentEdge


def test_subagent_compiler_passes_distinct_permissions_over_shared_workspace(
    monkeypatch,
) -> None:
    workspace = object()
    constructors: dict[str, dict[str, object]] = {}
    materialized_workspaces: list[object] = []

    def materialize(
        _references,
        _blocks,
        *,
        filesystem_mode,
        scope,
        owner_id,
        owner_name,
        workspace,
    ):
        assert filesystem_mode == "configured-shared"
        assert scope == "subagent"
        assert owner_id in {"reader-id", "writer-id"}
        materialized_workspaces.append(workspace)
        return SimpleNamespace(
            model=object(),
            model_provider="openai",
            model_name="fixture-model",
            system_prompt=None,
            tools=(),
            middleware=(),
            automation_middleware=(),
            custom_middleware=(),
            tool_choice=None,
            model_settings={},
            response_format=None,
            backend=workspace,
            initial_files={},
            permissions=(f"{owner_name}-permission",),
            skill_sources=(),
            exception_retry=None,
        )

    def capture_constructor(constructor, **_kwargs):
        constructors[str(constructor["name"])] = constructor
        return SimpleNamespace()

    monkeypatch.setattr(subagent_graphs, "construct_deep_agent", capture_constructor)
    nodes = {
        "reader-id": ResolvedSubagent(
            key="reader-id",
            component_name="Reader component",
            name="reader",
            description="Reads shared files.",
            references={},
            blocks={},
            filesystem_mode="configured-shared",
            automation={"hooks": [], "periodic": []},
            subagents=(),
        ),
        "writer-id": ResolvedSubagent(
            key="writer-id",
            component_name="Writer component",
            name="writer",
            description="Writes shared files.",
            references={},
            blocks={},
            filesystem_mode="configured-shared",
            automation={"hooks": [], "periodic": []},
            subagents=(),
        ),
    }

    compiled = SubagentGraphCompiler(
        workspace=workspace,
        materialize_profile=materialize,
        agent_input_observer=None,
    ).compile(
        roots=(
            ResolvedSubagentEdge(target_key="reader-id"),
            ResolvedSubagentEdge(target_key="writer-id"),
        ),
        nodes=nodes,
    )

    assert [item["name"] for item in compiled] == ["reader", "writer"]
    assert materialized_workspaces == [workspace, workspace]
    assert constructors["reader"]["backend"] is workspace
    assert constructors["writer"]["backend"] is workspace
    assert constructors["reader"]["permissions"] == ["reader-permission"]
    assert constructors["writer"]["permissions"] == ["writer-permission"]
