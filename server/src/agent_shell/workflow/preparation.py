from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agent_shell.automation.context import AutomationContext, immutable_request
from agent_shell.automation.loader import AutomationPluginLoader
from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.input_messages import validate_prepared_messages
from agent_shell.workflow.contracts import WorkflowDefinition


@dataclass(slots=True)
class WorkflowPreparationResult:
    messages: list[dict[str, Any]]
    initial_files: dict[str, str | bytes]
    variables: dict[Any, Any]
    artifact_rule: Callable[..., Any] | None = None
    artifact_transform: Callable[..., Any] | None = None
    artifact_minimum_text_bytes: int = 1


class _PreparationServices:
    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        self.artifact_rule: Callable[..., Any] | None = None
        self.artifact_transform: Callable[..., Any] | None = None
        self.artifact_minimum_text_bytes = 1

    def prepare_skill(self, _owner_id: str, name: str, *, mode: str) -> Path:
        if mode != "overlay":
            raise ValueError("workflow preparation only supports overlay skills")
        path = self._skills_dir / name
        if not path.is_dir():
            raise ValueError("the requested skill does not exist")
        return path

    def configure_artifact_commit(
        self,
        *,
        rule: Callable[..., Any] | None = None,
        transform: Callable[..., Any] | None = None,
        minimum_text_bytes: int = 1,
    ) -> None:
        if rule is not None and not callable(rule):
            raise TypeError("artifact commit rule must be callable")
        if transform is not None and not callable(transform):
            raise TypeError("artifact commit transform must be callable")
        if not isinstance(minimum_text_bytes, int) or minimum_text_bytes < 1:
            raise ValueError("minimum_text_bytes must be a positive integer")
        if self.artifact_rule is not None or self.artifact_transform is not None:
            raise ValueError("artifact commit policy was already configured")
        self.artifact_rule = rule
        self.artifact_transform = transform
        self.artifact_minimum_text_bytes = minimum_text_bytes


class WorkflowPreparationContext(AutomationContext):
    """Workflow-only preparation services; not part of Agent automation."""

    def configure_artifact_commit(
        self,
        *,
        rule: Callable[..., Any] | None = None,
        transform: Callable[..., Any] | None = None,
        minimum_text_bytes: int = 1,
    ) -> None:
        if self.stage != "prepare":
            raise ValueError("artifact commit policy is preparation-only")
        self._runtime.configure_artifact_commit(
            rule=rule,
            transform=transform,
            minimum_text_bytes=minimum_text_bytes,
        )


class WorkflowPreparationRuntime:
    def __init__(
        self,
        *,
        plugins_dir: Path,
        runtime_root: Path,
        skills_dir: Path,
        mapped_paths: dict[str, Path] | None = None,
    ) -> None:
        self._plugins_dir = plugins_dir
        self._runtime_root = runtime_root
        self._skills_dir = skills_dir
        self._mapped_paths = mapped_paths or {}

    async def prepare(
        self,
        definition: WorkflowDefinition,
        *,
        request_id: str,
        messages: list[dict[str, Any]],
    ) -> WorkflowPreparationResult:
        prepared_messages = list(messages)
        initial_files: dict[str, str | bytes] = {}
        variables: dict[Any, Any] = {}
        services = _PreparationServices(self._skills_dir)
        loader = AutomationPluginLoader(
            request_id=request_id,
            plugins_dir=self._plugins_dir,
            runtime_root=self._runtime_root,
        )
        try:
            for index, binding in enumerate(definition.preparation):
                if not binding.enabled:
                    continue
                function, plugin_dir = loader.entrypoint(
                    str(definition.public_id),
                    "workflow",
                    index,
                    binding.plugin_id,
                    "prepare",
                )
                if function is None:
                    continue
                context = WorkflowPreparationContext(
                    runtime=services,
                    request=immutable_request(request_id, prepared_messages),
                    owner_id=str(definition.public_id),
                    owner_type="workflow",
                    owner_name=definition.name,
                    binding_kind="workflow",
                    binding_index=index,
                    plugin_id=binding.plugin_id,
                    plugin_dir=plugin_dir,
                    runtime_dir=self._runtime_root,
                    mapped_paths=self._mapped_paths,
                    config=dict(binding.config),
                    variables=variables,
                    stage="prepare",
                    messages=prepared_messages,
                    initial_files=initial_files,
                )
                try:
                    await function(context)
                except Exception as exc:
                    raise AgentRuntimeError(
                        "workflow.preparation_failed",
                        "The Workflow preparation plugin failed.",
                        status_code=422,
                    ) from exc
        finally:
            loader.close()
        try:
            prepared_messages = validate_prepared_messages(prepared_messages)
        except AgentRuntimeError:
            raise
        except Exception as exc:
            raise AgentRuntimeError(
                "workflow.preparation_invalid_messages",
                "Workflow preparation produced invalid chat messages.",
                status_code=422,
            ) from exc
        return WorkflowPreparationResult(
            prepared_messages,
            initial_files,
            variables,
            artifact_rule=services.artifact_rule,
            artifact_transform=services.artifact_transform,
            artifact_minimum_text_bytes=services.artifact_minimum_text_bytes,
        )
