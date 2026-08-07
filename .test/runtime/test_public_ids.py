from agent_shell.auto.contracts import AutoDefinition
from agent_shell.contracts import MainAgentProfile
from agent_shell.workflow.contracts import WorkflowDefinition


def test_public_root_ids_default_to_prefix_and_configuration_name() -> None:
    agent = MainAgentProfile.model_validate({"name": "Research Agent"})
    workflow = WorkflowDefinition.model_validate(
        {
            "name": "Daily Report",
            "nodes": [
                {"id": "input", "type": "builtin.input.messages"},
                {"id": "output", "type": "builtin.output.message"},
            ],
        }
    )
    auto = AutoDefinition.model_validate(
        {"name": "Default Route", "source": "def route(messages): pass"}
    )

    assert agent.public_id == "agent-research-agent"
    assert workflow.public_id == "workflow-daily-report"
    assert auto.public_id == "auto-default-route"

