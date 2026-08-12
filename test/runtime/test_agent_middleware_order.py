from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent_shell.runtime import agent_builder, subagent_middleware
from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.runtime.agent_compilation import MaterializedAgentProfile
from agent_shell.validation.assembly import (
    ResolvedSubagent,
    ResolvedSubagentEdge,
    StaticAssembly,
)
from agent_shell.validation.models import ValidationReport

from .support import config


def _middleware(name: str, *, state_schema: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, tools=(), state_schema=state_schema)


def _profile(
    *,
    core: object,
    extra: object,
    retry: object,
    packages: tuple[object, ...],
) -> MaterializedAgentProfile:
    return MaterializedAgentProfile(
        model=object(),
        model_provider="openai",
        model_name="test-model",
        tool_choice=None,
        response_format=None,
        model_settings={"temperature": 0},
        exception_retry=SimpleNamespace(after_provider_boundary=(retry,)),
        system_prompt=None,
        tools=(),
        middleware=(core,),
        package_middleware=packages,
        extra_middleware=(extra,),
        session_recorder_middleware=None,
        backend=object(),
        initial_files={},
        skill_sources=(),
        permissions=(),
        workspace=SimpleNamespace(initial_files={}),
    )


def test_custom_package_middleware_is_the_shell_caller_tail_for_main_and_subagent(
    tmp_path,
    monkeypatch,
) -> None:
    main_core = _middleware("MainCore")
    main_extra = _middleware("MainBeforeAgent")
    main_retry = _middleware("MainRetry")
    main_packages = (
        _middleware("MainPackageOne", state_schema=object),
        _middleware("MainPackageTwo"),
    )
    child_core = _middleware("ChildCore")
    child_extra = _middleware("ChildBeforeAgent")
    child_retry = _middleware("ChildRetry")
    child_packages = (
        _middleware("ChildPackageOne"),
        _middleware("ChildPackageTwo"),
    )
    main_profile = _profile(
        core=main_core,
        extra=main_extra,
        retry=main_retry,
        packages=main_packages,
    )
    child_profile = _profile(
        core=child_core,
        extra=child_extra,
        retry=child_retry,
        packages=child_packages,
    )

    child = ResolvedSubagent(
        key="child-id",
        component_name="Worker component",
        name="worker",
        description="Handles delegated work.",
        references={},
        blocks={},
        filesystem_mode="configured-shared",
    )
    output_mode = {
        "id": "output-id",
        "name": "Output",
        **config(mode="blocklist"),
    }
    assembly = StaticAssembly(
        main_agent={"id": "main-id", "name": "Main Agent"},
        references={"model": "model-id", "output-mode": "output-id"},
        blocks={
            "model": {"id": "model-id"},
            "output-mode": output_mode,
            "subagent": {
                "instruction_override": None,
                "task_description_override": "Delegate work.",
            },
        },
        filesystem_mode="configured-shared",
        disabled_capabilities=frozenset(),
        subagents=(ResolvedSubagentEdge(target_key=child.key),),
        subagent_nodes={child.key: child},
    )
    validation = SimpleNamespace(
        resolve_main_agent=lambda *_args, **_kwargs: (
            ValidationReport(stage="request_assembly", issues=()),
            assembly,
        )
    )
    builder = AgentBuilder(
        SimpleNamespace(),
        custom_tools_dir=tmp_path / "tools",
        middleware_packages_dir=tmp_path / "middleware",
        runtime_dir=tmp_path / "runtime",
        skills_dir=tmp_path / "skills",
        validation=validation,
        provider_http_clients=SimpleNamespace(),
    )

    def materialize(*_args, scope: str, **_kwargs):
        return child_profile if scope == "subagent" else main_profile

    monkeypatch.setattr(builder, "_materialize_profile", materialize)
    middleware_runtime = SimpleNamespace()
    monkeypatch.setattr(
        agent_builder.MiddlewarePackageRuntime,
        "from_assembly",
        classmethod(lambda _cls, *_args, **_kwargs: middleware_runtime),
    )
    captured: dict[str, object] = {}

    def capture_constructor(constructor, **_kwargs):
        captured["constructor"] = constructor
        return object()

    monkeypatch.setattr(agent_builder, "construct_deep_agent", capture_constructor)
    delegation = _middleware("SubAgentMiddleware")

    def capture_delegation(*, middleware, **_kwargs):
        captured["delegation_input"] = tuple(middleware)
        return delegation

    monkeypatch.setattr(
        subagent_middleware,
        "make_subagent_middleware_override",
        capture_delegation,
    )

    asyncio.run(
        builder.build(
            "main-id",
            [{"role": "user", "content": "Hello"}],
        )
    )

    constructor = captured["constructor"]
    main_middleware = constructor["middleware"]
    child_middleware = constructor["subagents"][0]["middleware"]
    delegation_input = captured["delegation_input"]

    assert main_middleware[-2:] == list(main_packages)
    assert child_middleware[-2:] == list(child_packages)
    assert main_middleware.index(main_extra) < main_middleware.index(main_packages[0])
    assert child_middleware.index(child_extra) < child_middleware.index(child_packages[0])
    assert main_middleware.index(main_retry) < main_middleware.index(main_packages[0])
    assert child_middleware.index(child_retry) < child_middleware.index(child_packages[0])
    assert main_middleware.index(delegation) < main_middleware.index(main_packages[0])
    assert delegation_input[-2:] == main_packages
