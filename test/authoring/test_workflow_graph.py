from __future__ import annotations

from copy import deepcopy
import asyncio

import pytest
from deepagents.backends import StateBackend
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.agent_builder import BuiltAgent
from agent_shell.runtime.agent_runtime import AgentRuntime
from agent_shell.runtime.context import WorkflowRuntimeContext
from agent_shell.runtime.state import AgentShellState
from agent_shell.validation.assembly import StaticAssembly
from agent_shell.validation import ValidationIssue, ValidationReport
from agent_shell.workflow import (
    NODE_CATALOG,
    admit_workflow_document,
    compile_workflow,
    validate_workflow_executable,
    workflow_document_sha256,
    workflow_executable_sha256,
)


AGENT_A = "11111111-1111-4111-8111-111111111111"
AGENT_B = "22222222-2222-4222-8222-222222222222"


def graph_payload(*agent_ids: str) -> dict[str, object]:
    nodes = [{"id": "start", "type": "start", "type_version": 1, "config": {}}]
    nodes.extend(
        {
            "id": f"agent-{index}",
            "type": "agent",
            "type_version": 1,
            "config": {"main_agent_id": agent_id},
        }
        for index, agent_id in enumerate(agent_ids, start=1)
    )
    nodes.append({"id": "end", "type": "end", "type_version": 1, "config": {}})

    edges = []
    sequence = [str(node["id"]) for node in nodes]
    for source, target in zip(sequence, sequence[1:]):
        edges.append(
            {
                "id": f"{source}-{target}",
                "source": source,
                "source_handle": "next",
                "target": target,
                "target_handle": "in",
            }
        )

    return {
        "definition": {
            "schema_version": 1,
            "state_contract": "agent-shell.workflow.messages.v1",
            "nodes": nodes,
            "edges": edges,
        },
        "layout": {
            "nodes": {
                node_id: {"x": index * 240, "y": 160}
                for index, node_id in enumerate(sequence)
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    }


def valid_main_agent(_main_agent_id: str) -> ValidationReport:
    return ValidationReport(stage="workflow_publish")


def test_catalog_exposes_the_first_supported_node_and_handle_paradigms() -> None:
    assert [item.type for item in NODE_CATALOG] == ["start", "agent", "end"]
    assert [item.runtime_kind for item in NODE_CATALOG] == [
        "graph_entry",
        "compiled_subgraph",
        "graph_exit",
    ]
    assert [handle.id for handle in NODE_CATALOG[0].output_handles] == ["next"]
    assert [handle.id for handle in NODE_CATALOG[1].input_handles] == ["in"]
    assert [handle.id for handle in NODE_CATALOG[1].output_handles] == ["next"]
    assert [handle.id for handle in NODE_CATALOG[2].input_handles] == ["in"]
    assert {
        handle.edge_type for item in NODE_CATALOG for handle in (
            *item.input_handles,
            *item.output_handles,
        )
    } == {"normal"}
    assert all(
        handle.max_connections is None
        for item in NODE_CATALOG
        for handle in (*item.input_handles, *item.output_handles)
    )
    assert NODE_CATALOG[1].config_model.model_json_schema()["required"] == [
        "main_agent_id"
    ]


def test_admission_accepts_incomplete_drafts_and_layout_does_not_change_execution_sha() -> None:
    incomplete = graph_payload(AGENT_A)
    incomplete["definition"]["edges"] = []  # type: ignore[index]

    admission, admitted = admit_workflow_document(incomplete)

    assert admission.valid is True
    assert admitted is not None
    executable = validate_workflow_executable(
        admitted,
        validate_main_agent=valid_main_agent,
    )
    assert executable.valid is True

    complete_report, complete = admit_workflow_document(graph_payload(AGENT_A))
    assert complete_report.valid is True
    assert complete is not None
    moved = complete.model_copy(
        update={
            "layout": complete.layout.model_copy(
                update={
                    "viewport": complete.layout.viewport.model_copy(
                        update={"x": 320.0, "zoom": 1.5}
                    )
                }
            )
        }
    )
    assert workflow_document_sha256(complete) != workflow_document_sha256(moved)
    assert workflow_executable_sha256(
        complete.definition
    ) == workflow_executable_sha256(moved.definition)

    reordered = complete.model_copy(
        update={
            "definition": complete.definition.model_copy(
                update={
                    "nodes": list(reversed(complete.definition.nodes)),
                    "edges": list(reversed(complete.definition.edges)),
                }
            )
        }
    )
    assert workflow_document_sha256(complete) == workflow_document_sha256(reordered)
    assert workflow_executable_sha256(
        complete.definition
    ) == workflow_executable_sha256(reordered.definition)


@pytest.mark.parametrize(
    ("mutate", "expected_code", "expected_path"),
    [
        (
            lambda payload: payload["definition"]["nodes"][1].update(type="unknown"),
            "workflow.node_type_unsupported",
            "definition.nodes[1].type",
        ),
        (
            lambda payload: payload["definition"]["nodes"][1].update(
                type_version=2
            ),
            "workflow.node_version_unsupported",
            "definition.nodes[1].type_version",
        ),
        (
            lambda payload: payload["definition"]["nodes"][1]["config"].update(
                unexpected=True
            ),
            "contract.unknown_field",
            "definition.nodes[1].config.unexpected",
        ),
        (
            lambda payload: payload["definition"]["nodes"][1].update(id="start"),
            "workflow.node_id_duplicate",
            "definition.nodes[1].id",
        ),
        (
            lambda payload: payload["layout"]["nodes"].update(
                orphan={"x": 1, "y": 1}
            ),
            "workflow.layout_node_not_found",
            "layout.nodes.orphan",
        ),
    ],
)
def test_admission_rejects_unsupported_or_ambiguous_graph_documents(
    mutate,
    expected_code: str,
    expected_path: str,
) -> None:
    payload = deepcopy(graph_payload(AGENT_A))
    mutate(payload)

    report, document = admit_workflow_document(payload)

    assert document is None
    assert any(
        issue.code == expected_code and issue.path == expected_path
        for issue in report.issues
    )


@pytest.mark.parametrize(
    ("agent_ids", "expected_validated"),
    [
        ((AGENT_A,), [AGENT_A]),
        ((AGENT_A, AGENT_B), [AGENT_A, AGENT_B]),
        ((AGENT_A, AGENT_A), [AGENT_A]),
    ],
)
def test_executable_validation_accepts_one_or_more_agent_linear_graphs(
    agent_ids: tuple[str, ...],
    expected_validated: list[str],
) -> None:
    admission, document = admit_workflow_document(graph_payload(*agent_ids))
    seen: list[str] = []

    def validate(main_agent_id: str) -> ValidationReport:
        seen.append(main_agent_id)
        return ValidationReport(stage="workflow_publish")

    assert admission.valid is True
    assert document is not None
    report = validate_workflow_executable(document, validate_main_agent=validate)

    assert report.valid is True
    assert seen == expected_validated


def test_executable_validation_accepts_multiple_normal_inputs_and_outputs() -> None:
    payload = graph_payload(AGENT_A, AGENT_B)
    payload["definition"]["edges"] = [  # type: ignore[index]
        {
            "id": "start-agent-1",
            "source": "start",
            "source_handle": "next",
            "target": "agent-1",
            "target_handle": "in",
        },
        {
            "id": "agent-1-agent-2",
            "source": "agent-1",
            "source_handle": "next",
            "target": "agent-2",
            "target_handle": "in",
        },
        {
            "id": "agent-1-end",
            "source": "agent-1",
            "source_handle": "next",
            "target": "end",
            "target_handle": "in",
        },
        {
            "id": "agent-2-end",
            "source": "agent-2",
            "source_handle": "next",
            "target": "end",
            "target_handle": "in",
        },
    ]
    admission, document = admit_workflow_document(payload)

    assert admission.valid is True
    assert document is not None
    assert validate_workflow_executable(
        document,
        validate_main_agent=valid_main_agent,
    ).valid is True


def test_topology_does_not_forbid_langgraph_cycles() -> None:
    payload = graph_payload(AGENT_A, AGENT_B)
    payload["definition"]["edges"] = [  # type: ignore[index]
        *payload["definition"]["edges"],  # type: ignore[index]
        {
            "id": "agent-2-agent-1",
            "source": "agent-2",
            "source_handle": "next",
            "target": "agent-1",
            "target_handle": "in",
        },
    ]
    admission, document = admit_workflow_document(payload)

    assert admission.valid is True
    assert document is not None
    assert validate_workflow_executable(
        document,
        validate_main_agent=valid_main_agent,
    ).valid is True


def test_executable_validation_attaches_main_agent_issues_to_the_agent_node() -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A))
    assert admission.valid is True
    assert document is not None

    def missing_main_agent(main_agent_id: str) -> ValidationReport:
        return ValidationReport(
            stage="workflow_publish",
            issues=(
                ValidationIssue(
                    code="assembly.main_agent_not_found",
                    scope="main_agent",
                    owner_id=main_agent_id,
                    path="id",
                    message="The requested Main Agent does not exist.",
                    message_key="validation.issue.assembly.mainAgentNotFound",
                ),
            ),
        )

    report = validate_workflow_executable(
        document,
        validate_main_agent=missing_main_agent,
    )

    assert report.valid is False
    issue = next(
        item for item in report.issues if item.code == "assembly.main_agent_not_found"
    )
    assert issue.owner_id == "agent-1"
    assert issue.owner_type == "agent"
    assert issue.path == "definition.nodes[1].config.main_agent_id"


def test_compiler_maps_canvas_start_and_end_to_langgraph_sentinels() -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A))
    assert admission.valid is True
    assert document is not None

    def answer(_state: AgentShellState) -> dict[str, list[AIMessage]]:
        return {"messages": [AIMessage(content="compiled workflow response")]}

    agent_graph = (
        StateGraph(AgentShellState)
        .add_node("answer", answer)
        .add_edge(START, "answer")
        .add_edge("answer", END)
        .compile()
    )
    graph = compile_workflow(document, node_graphs={"agent-1": agent_graph})

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [],
                "shared_vars": {},
            }
        )
    )

    assert [message.type for message in result["messages"]] == ["ai"]
    assert result["messages"][-1].content == "compiled workflow response"


def test_compiler_maps_every_agent_node_to_a_compiled_subgraph() -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A, AGENT_B))
    assert admission.valid is True
    assert document is not None

    def answer(content: str):
        def node(_state: AgentShellState) -> dict[str, list[AIMessage]]:
            return {"messages": [AIMessage(content=content)]}

        return (
            StateGraph(AgentShellState)
            .add_node("answer", node)
            .add_edge(START, "answer")
            .add_edge("answer", END)
            .compile()
        )

    graph = compile_workflow(
        document,
        node_graphs={
            "agent-1": answer("first agent"),
            "agent-2": answer("second agent"),
        },
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [],
                "shared_vars": {},
            }
        )
    )

    assert [message.content for message in result["messages"]] == [
        "first agent",
        "second agent",
    ]


@pytest.mark.parametrize(
    ("state_mode", "expected_seen"),
    [("shared", {"agent-1": 0, "agent-2": 1}), ("isolated", {"agent-1": 0, "agent-2": 0})],
)
def test_workflow_state_mode_controls_message_inheritance_and_merges_sessions(
    state_mode: str,
    expected_seen: dict[str, int],
) -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A, AGENT_B))
    assert admission.valid is True
    assert document is not None

    def agent_graph(node_id: str):
        def answer(state: AgentShellState) -> dict[str, object]:
            seen = len(state.get("messages", []))
            return {
                "messages": [AIMessage(content=node_id)],
                "agent_sessions": {node_id: {"seen": seen}},
            }

        return (
            StateGraph(AgentShellState)
            .add_node("answer", answer)
            .add_edge(START, "answer")
            .add_edge("answer", END)
            .compile()
        )

    graph = compile_workflow(
        document,
        node_graphs={
            "agent-1": agent_graph("agent-1"),
            "agent-2": agent_graph("agent-2"),
        },
        state_mode=state_mode,
    )
    input_state: dict[str, object] = {"shared_vars": {}, "agent_sessions": {}}
    if state_mode == "shared":
        input_state["messages"] = []

    result = asyncio.run(graph.ainvoke(input_state))

    assert {
        session_id: record["seen"]
        for session_id, record in result["agent_sessions"].items()
    } == expected_seen
    if state_mode == "shared":
        assert [message.content for message in result["messages"]] == [
            "agent-1",
            "agent-2",
        ]
    else:
        assert "messages" not in result


def test_isolated_parallel_agents_share_one_snapshot_and_merge_public_channels() -> None:
    payload = graph_payload(AGENT_A, AGENT_B)
    payload["definition"]["edges"] = [  # type: ignore[index]
        {
            "id": "start-agent-1",
            "source": "start",
            "source_handle": "next",
            "target": "agent-1",
            "target_handle": "in",
        },
        {
            "id": "start-agent-2",
            "source": "start",
            "source_handle": "next",
            "target": "agent-2",
            "target_handle": "in",
        },
        {
            "id": "agent-1-end",
            "source": "agent-1",
            "source_handle": "next",
            "target": "end",
            "target_handle": "in",
        },
        {
            "id": "agent-2-end",
            "source": "agent-2",
            "source_handle": "next",
            "target": "end",
            "target_handle": "in",
        },
    ]
    admission, document = admit_workflow_document(payload)
    assert admission.valid is True
    assert document is not None

    def agent_graph(node_id: str):
        def answer(state: AgentShellState) -> dict[str, object]:
            seen = len(state.get("messages", []))
            return {
                "messages": [AIMessage(content=node_id)],
                "shared_vars": {node_id: seen},
                "agent_sessions": {node_id: {"seen": seen}},
            }

        return (
            StateGraph(AgentShellState)
            .add_node("answer", answer)
            .add_edge(START, "answer")
            .add_edge("answer", END)
            .compile()
        )

    graph = compile_workflow(
        document,
        node_graphs={
            "agent-1": agent_graph("agent-1"),
            "agent-2": agent_graph("agent-2"),
        },
        state_mode="isolated",
    )

    result = asyncio.run(
        graph.ainvoke({"shared_vars": {}, "agent_sessions": {}})
    )

    assert result["shared_vars"] == {"agent-1": 0, "agent-2": 0}
    assert result["agent_sessions"] == {
        "agent-1": {"seen": 0},
        "agent-2": {"seen": 0},
    }
    assert "messages" not in result


def test_workflow_agent_nodes_share_official_state_backend_files() -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A, AGENT_B))
    assert admission.valid is True
    assert document is not None
    backend = StateBackend()

    def agent_graph(*, write: bool):
        def node(_state: AgentShellState) -> dict[str, list[AIMessage]]:
            if write:
                backend.write("/shared.txt", "from first Agent node")
            else:
                result = backend.read("/shared.txt")
                assert result.error is None
                assert result.file_data is not None
                assert result.file_data["content"] == "from first Agent node"
            return {"messages": [AIMessage(content="ok")]}

        return (
            StateGraph(
                AgentShellState,
                context_schema=WorkflowRuntimeContext,
            )
            .add_node("filesystem", node)
            .add_edge(START, "filesystem")
            .add_edge("filesystem", END)
            .compile()
        )

    graph = compile_workflow(
        document,
        node_graphs={
            "agent-1": agent_graph(write=True),
            "agent-2": agent_graph(write=False),
        },
    )

    result = asyncio.run(
        graph.ainvoke(
            {"messages": [], "shared_vars": {}, "files": {}},
            context=WorkflowRuntimeContext(),
        )
    )

    assert result["files"]["/shared.txt"]["content"] == "from first Agent node"


def test_runtime_builds_repeated_main_agent_references_per_workflow_node() -> None:
    admission, document = admit_workflow_document(graph_payload(AGENT_A, AGENT_A))
    assert admission.valid is True
    assert document is not None

    class MiddlewareRuntime:
        async def close(self) -> None:
            return None

    class RecordingRuntime(AgentRuntime):
        def __init__(self) -> None:
            self.built_ids: list[str] = []
            self.built_nodes: list[str] = []
            self._blocks = None
            self._workflow_debug = None
            self._runtime_diagnostics = None
            self._builder = type(
                "Builder",
                (),
                {
                    "resolve": staticmethod(
                        lambda main_agent_id, **_kwargs: StaticAssembly(
                            main_agent={"id": main_agent_id, "name": "Repeated Agent"},
                            references={},
                            blocks={},
                            filesystem_mode="configured-shared",
                            disabled_capabilities=frozenset(),
                            subagents=(),
                            subagent_nodes={},
                        )
                    )
                },
            )()

        async def build_resolved_agent(self, assembly, _raw_messages, **kwargs):
            main_agent_id = str(assembly.main_agent["id"])
            self.built_ids.append(main_agent_id)
            self.built_nodes.append(str(kwargs["workflow_node_id"]))

            def answer(_state: AgentShellState) -> dict[str, list[AIMessage]]:
                return {"messages": [AIMessage(content=main_agent_id)]}

            graph = (
                StateGraph(AgentShellState)
                .add_node("answer", answer)
                .add_edge(START, "answer")
                .add_edge("answer", END)
                .compile()
            )
            return BuiltAgent(
                graph=graph,
                input_state={"messages": [], "shared_vars": {}},
                output_config={},
                agent_id=main_agent_id,
                agent_name="Repeated Agent",
                subagent_profile_ids={},
                middleware_runtime=MiddlewareRuntime(),  # type: ignore[arg-type]
            )

        def _execution(self, built: BuiltAgent, **kwargs):
            return {"built": built, **kwargs}

    runtime = RecordingRuntime()
    execution = asyncio.run(
        runtime.start_workflow(
            document,
            [{"role": "user", "content": "Run the Workflow."}],
            workflow_filesystem_id="33333333-3333-4333-8333-333333333333",
        )
    )

    assert runtime.built_ids == [AGENT_A, AGENT_A]
    assert runtime.built_nodes == ["agent-1", "agent-2"]
    assert [node_id for node_id, _ in execution["workflow_built"]] == [
        "agent-1",
        "agent-2",
    ]
    result = asyncio.run(
        execution["graph"].ainvoke({"messages": [], "shared_vars": {}})
    )
    assert [message.content for message in result["messages"]] == [AGENT_A, AGENT_A]
