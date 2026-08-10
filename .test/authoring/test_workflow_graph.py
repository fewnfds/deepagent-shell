from __future__ import annotations

from copy import deepcopy
import asyncio

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agent_shell.runtime.state import AgentShellState
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


def test_catalog_exposes_only_the_first_supported_node_and_handle_paradigms() -> None:
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
    assert executable.valid is False
    assert {
        issue.code for issue in executable.issues
    } >= {
        "workflow.node_input_cardinality_invalid",
        "workflow.node_output_cardinality_invalid",
    }

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


@pytest.mark.parametrize("agent_ids", [(AGENT_A,), (AGENT_A, AGENT_B)])
def test_executable_validation_accepts_one_or_more_agent_linear_graphs(
    agent_ids: tuple[str, ...],
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
    assert seen == list(agent_ids)


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
    graph = compile_workflow(document, agent_graphs={"agent-1": agent_graph})

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
