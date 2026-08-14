from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from agent_shell.storage.file_config import FileConfigRepository

if TYPE_CHECKING:
    from agent_shell.runtime.output_stream import OutputEvent


class WorkflowEventOutputSettings(BaseModel):
    """Global projection setting for the Workflow full-state stream event."""

    model_config = ConfigDict(extra="forbid")

    values: bool = False

    def allows(self, event: "OutputEvent") -> bool:
        if event.workflow_event_kind == "values":
            return self.values
        return True


class WorkflowEventOutputSettingsStore:
    """Persist Workflow event projection settings in system.yaml."""

    def __init__(self, repository: FileConfigRepository) -> None:
        self._repository = repository

    def snapshot(self) -> WorkflowEventOutputSettings:
        raw = self._repository.system().get("workflow_event_output", {})
        return WorkflowEventOutputSettings.model_validate(raw)

    def update(
        self, settings: WorkflowEventOutputSettings
    ) -> WorkflowEventOutputSettings:
        payload = settings.model_dump(mode="json")
        self._repository.update_system(
            lambda system: system.__setitem__("workflow_event_output", payload)
        )
        return self.snapshot()


__all__ = ["WorkflowEventOutputSettings", "WorkflowEventOutputSettingsStore"]
