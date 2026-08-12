from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_shell.middleware_packages.validation import MiddlewarePackageValidationService
from agent_shell.provider_http import ProviderHttpClients
from agent_shell.provider_secrets import ProviderSecretResolver
from agent_shell.runtime.agent_builder import AgentBuilder
from agent_shell.runtime.agent_runtime import AgentExecution, AgentRuntime
from agent_shell.runtime.diagnostics import RuntimeDiagnostics
from agent_shell.runtime.workflow_debug import WorkflowDebugService
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.storage.file_config import FileConfigRepository
from agent_shell.storage.media_outputs import MediaOutputStore
from agent_shell.storage.workflows import WorkflowStore
from agent_shell.validation.assembly import StaticAssembly
from agent_shell.validation.models import ValidationReport
from agent_shell.validation.service import ConfigurationValidationService


@dataclass(slots=True)
class RequestRuntimeSnapshot:
    """Resolve and build exactly one Agent from one immutable file configuration view."""

    _configs: AgentConfigStore
    _workflows: WorkflowStore
    _validation: ConfigurationValidationService
    _runtime: AgentRuntime
    _repository: FileConfigRepository

    def main_agent_by_name(self, name: str) -> dict[str, Any] | None:
        return self._configs.get_item_by_name("main_agents", name)

    def workflow_by_name(self, name: str) -> dict[str, Any] | None:
        return self._workflows.get_item_by_name(name)

    def resolve_main_agent(
        self,
        main_agent_id: str,
        *,
        workflow_filesystem_id: str,
    ) -> tuple[ValidationReport, StaticAssembly | None]:
        return self._validation.resolve_main_agent(
            main_agent_id,
            workflow_filesystem_id=workflow_filesystem_id,
        )

    def close(self) -> None:
        # The repository clone owns no external handles. Keeping this method
        # preserves the request lifecycle boundary used by AgentRuntime.
        return None

    async def start_agent(self, main_agent_id: str, raw_messages: object, **kwargs: Any) -> AgentExecution:
        try:
            return await self._runtime.start(main_agent_id, raw_messages, **kwargs)
        finally:
            self.close()

    async def start_workflow(self, workflow: Mapping[str, Any], raw_messages: object, **kwargs: Any) -> AgentExecution:
        try:
            document = self._workflows.get_graph(str(workflow["id"]))
            if document is None:
                raise RuntimeError("the captured Workflow no longer exists")
            return await self._runtime.start_workflow(
                document,
                raw_messages,
                workflow_filesystem_id=str(workflow["filesystem_id"]),
                workflow_snapshot=workflow,
                **kwargs,
            )
        finally:
            self.close()


class RequestSnapshotRuntime:
    """Capture the latest committed file configuration for each Agent construction."""

    def __init__(
        self,
        configuration: FileConfigRepository,
        *,
        custom_tools_dir: Path,
        middleware_packages_dir: Path,
        runtime_dir: Path,
        skills_dir: Path,
        provider_http_clients: ProviderHttpClients,
        media_outputs: MediaOutputStore,
        workflow_debug: WorkflowDebugService,
        runtime_diagnostics: RuntimeDiagnostics,
    ) -> None:
        self._configuration = configuration
        self._custom_tools_dir = custom_tools_dir
        self._middleware_packages_dir = middleware_packages_dir
        self._runtime_dir = runtime_dir
        self._skills_dir = skills_dir
        self._provider_http_clients = provider_http_clients
        self._media_outputs = media_outputs
        self._workflow_debug = workflow_debug
        self._runtime_diagnostics = runtime_diagnostics

    def capture(self) -> RequestRuntimeSnapshot:
        repository = self._configuration.clone()
        try:
            blocks = BlockStore(repository)
            configs = AgentConfigStore(repository)
            workflows = WorkflowStore(repository)
            secrets = ProviderSecretResolver(repository)
            middleware_package_validation = MiddlewarePackageValidationService(
                packages_dir=self._middleware_packages_dir,
                runtime_root=self._runtime_dir,
            )
            validation = ConfigurationValidationService(
                blocks,
                configs,
                middleware_package_validation,
                custom_tools_dir=self._custom_tools_dir,
            )
            runtime = AgentRuntime(
                AgentBuilder(
                    secrets,
                    custom_tools_dir=self._custom_tools_dir,
                    middleware_packages_dir=self._middleware_packages_dir,
                    runtime_dir=self._runtime_dir,
                    skills_dir=self._skills_dir,
                    validation=validation,
                    provider_http_clients=self._provider_http_clients,
                ),
                self._media_outputs,
                blocks=blocks,
                workflow_debug=self._workflow_debug,
                runtime_diagnostics=self._runtime_diagnostics,
            )
            return RequestRuntimeSnapshot(
                _configs=configs,
                _workflows=workflows,
                _validation=validation,
                _runtime=runtime,
                _repository=repository,
            )
        except Exception:
            raise
