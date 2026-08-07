from __future__ import annotations

from langchain_core.outputs import ChatGeneration, ChatResult

from .support import *


def _tool_signature(tools) -> list[tuple[str, str, dict]]:
    return [
        (tool.name, tool.description, tool.args_schema.model_json_schema())
        for tool in tools
    ]


def _message_pairs(messages: list[object]) -> list[tuple[str, str]]:
    return [(message.type, message.text) for message in messages]


def test_user_configured_a_b_c_cycle_keeps_the_shared_prefix_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MainAgentModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        tool_signatures: ClassVar[list[list[tuple[str, str, dict]]]] = []

        def bind_tools(self, tools, **_kwargs):
            type(self).tool_signatures.append(_tool_signature(tools))
            return self

    class WorkerModel(ToolCallingFakeModel):
        seen_messages: ClassVar[list[list[object]]] = []
        tool_signatures: ClassVar[list[list[tuple[str, str, dict]]]] = []

        def bind_tools(self, tools, **_kwargs):
            type(self).tool_signatures.append(_tool_signature(tools))
            return self

        def _generate(self, messages, *args, **kwargs):
            type(self).seen_messages.append(list(messages))
            if any(isinstance(message, ToolMessage) for message in messages):
                response = AIMessage(content="B completed after C")
            else:
                task = next(
                    message.text
                    for message in reversed(messages)
                    if message.type == "human"
                )
                if task == "Run B and then C.":
                    response = AIMessage(
                        content="",
                        tool_calls=[{
                            "name": "task",
                            "args": {
                                "description": "Run C only.",
                                "subagent_type": "worker",
                            },
                            "id": "call-b-to-c",
                            "type": "tool_call",
                        }],
                    )
                else:
                    assert task == "Run C only."
                    response = AIMessage(content="C completed")
            return ChatResult(generations=[ChatGeneration(message=response)])

    main_agent_model = MainAgentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "task",
                    "args": {
                        "description": "Run B and then C.",
                        "subagent_type": "worker",
                    },
                    "id": "call-a-to-b",
                    "type": "tool_call",
                }],
            ),
            AIMessage(content="A completed"),
        ]
    )
    worker_model = WorkerModel(responses=[AIMessage(content="unused")])
    model_build_count = 0
    model_blocks: list[dict] = []

    def build_model(block, _credential, _http_clients):
        nonlocal model_build_count
        model_build_count += 1
        model_blocks.append(block)
        return main_agent_model if model_build_count == 1 else worker_model

    common_system_prompt = (
        "You are Xiao Ai, one of infinitely cloned writers with the same "
        "memory and capabilities. Work together to complete the task."
    )
    shared_replacement = "SHARED LONG CONTEXT\n" + ("source material " * 512)
    worker_description = "Complete one delegated unit of the shared writing task."
    task_description = (
        "Delegate one complete unit of work to this catalog:\n"
        "{available_agents}"
    )

    with make_client(tmp_path, monkeypatch) as client:
        monkeypatch.setattr(
            "agent_shell.runtime.agent_builder._build_chat_model",
            build_model,
        )
        main_agent = create_main_agent(client)
        system_prompt = client.post(
            "/api/blocks/system-prompt",
            json={
                "name": "Shared clone identity",
                "system_prompt": common_system_prompt,
            },
        ).json()

        write_automation_script(
            tmp_path,
            "prepare-shared-prefix",
            "from agent_shell.automation.messages import mutable_request_messages\n"
            "\n"
            "async def prepare(ctx):\n"
            "    tag = str(ctx.config['tag'])\n"
            "    replacement = str(ctx.config['replacement'])\n"
            "    ctx.messages.extend(mutable_request_messages(ctx.request.messages))\n"
            "    for message in ctx.messages:\n"
            "        if message.get('role') == 'user':\n"
            "            message['content'] = message['content'].replace(tag, replacement)\n"
            "    ctx.messages.extend([\n"
            "        {'role': 'user', 'content': str(ctx.config['role'])},\n"
            "        {'role': 'assistant', 'content': str(ctx.config['ready'])},\n"
            "    ])\n",
            config_schema=automation_config_schema(
                {
                    "tag": "string",
                    "replacement": "string",
                    "role": "string",
                    "ready": "string",
                },
                required=("tag", "replacement", "role", "ready"),
            ),
        )

        def automation(role: str, ready: str) -> dict[str, object]:
            return {
                "hooks": [{
                    "plugin_id": "prepare-shared-prefix",
                    "enabled": True,
                    "config": {
                        "tag": "[[SHARED_CONTEXT]]",
                        "replacement": shared_replacement,
                        "role": role,
                        "ready": ready,
                    },
                }],
                "periodic": [],
            }

        main_agent_automation = automation(
            "MAIN AGENT ROLE: read files, plan the work, and delegate units.",
            "MAIN AGENT READY",
        )
        worker_automation = automation(
            "WORKER ROLE: execute the delegated unit using the shared context.",
            "WORKER READY",
        )
        delegation = client.post(
            "/api/blocks/subagent",
            json={
                "name": "Cache-aligned delegation",
                "task_description_override": task_description,
            },
        ).json()
        def worker_payload(children: list[dict[str, str]] | None = None) -> dict:
            payload = subagent_payload(
                "worker-placeholder",
                name="worker",
                description=worker_description,
                subagents=children,
            )
            payload["settings"]["automation"] = {
                "hooks": worker_automation["hooks"],
                "periodic": [],
            }
            return payload

        b_payload = worker_payload()
        b_payload["component_name"] = "B"
        b = client.post(
            "/api/subagents",
            json=b_payload,
        ).json()
        c_payload = worker_payload()
        c_payload["component_name"] = "C"
        c = client.post(
            "/api/subagents",
            json=c_payload,
        ).json()
        b_payload = worker_payload([{"subagent_id": c["id"]}])
        b_payload["component_name"] = "B"
        b_response = client.put(
            f"/api/subagents/{b['id']}",
            json=b_payload,
        )
        assert b_response.status_code == 200, b_response.text
        c_payload = worker_payload([{"subagent_id": b["id"]}])
        c_payload["component_name"] = "C"
        c_response = client.put(
            f"/api/subagents/{c['id']}",
            json=c_payload,
        )
        assert c_response.status_code == 200, c_response.text
        a_response = client.put(
            f"/api/main-agents/{main_agent['id']}",
            json={
                "name": "A",
                "capability_refs": [
                    *main_agent["capability_refs"],
                    {"type": "system-prompt", "block_id": system_prompt["id"]},
                    {"type": "subagent", "block_id": delegation["id"]},
                ],
                "subagents": [{"subagent_id": b["id"]}],
                "automation": main_agent_automation,
            },
        )
        assert a_response.status_code == 200, a_response.text
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "A",
                "messages": [
                    {"role": "system", "content": "CLIENT SYSTEM"},
                    {
                        "role": "user",
                        "content": "[[SHARED_CONTEXT]]\nWrite the complete story.",
                    },
                    {"role": "assistant", "content": "Context acknowledged."},
                    {"role": "user", "content": "Begin the work."},
                ],
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["choices"][0]["message"]["content"].endswith(
        "A completed"
    )
    assert model_build_count == 3
    assert model_blocks[1:] == [model_blocks[0], model_blocks[0]]
    assert len(MainAgentModel.tool_signatures) >= 1
    assert len(WorkerModel.tool_signatures) >= 2
    expected_tools = MainAgentModel.tool_signatures[0]
    assert all(signature == expected_tools for signature in WorkerModel.tool_signatures)
    assert [item[0] for item in expected_tools] == ["read_file", "task"]

    main_agent_messages = _message_pairs(MainAgentModel.seen_messages[0])
    b_messages = _message_pairs(WorkerModel.seen_messages[0])
    c_messages = _message_pairs(WorkerModel.seen_messages[1])
    main_agent_start = main_agent_messages.index((
        "human",
        "MAIN AGENT ROLE: read files, plan the work, and delegate units.",
    ))
    b_start = b_messages.index((
        "human",
        "WORKER ROLE: execute the delegated unit using the shared context.",
    ))
    c_start = c_messages.index((
        "human",
        "WORKER ROLE: execute the delegated unit using the shared context.",
    ))
    assert main_agent_messages[:main_agent_start] == b_messages[:b_start]
    assert main_agent_messages[:main_agent_start] == c_messages[:c_start]
    assert ("human", shared_replacement + "\nWrite the complete story.") in (
        main_agent_messages[:main_agent_start]
    )
    assert main_agent_messages[main_agent_start:] == [
        (
            "human",
        "MAIN AGENT ROLE: read files, plan the work, and delegate units.",
        ),
        ("ai", "MAIN AGENT READY"),
    ]
    assert b_messages[b_start:] == [
        (
            "human",
            "WORKER ROLE: execute the delegated unit using the shared context.",
        ),
        ("ai", "WORKER READY"),
        ("human", "Run B and then C."),
    ]
    assert c_messages[c_start:] == [
        (
            "human",
            "WORKER ROLE: execute the delegated unit using the shared context.",
        ),
        ("ai", "WORKER READY"),
        ("human", "Run C only."),
    ]
