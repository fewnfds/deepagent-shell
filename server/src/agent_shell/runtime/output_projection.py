from __future__ import annotations

from collections.abc import Mapping

from agent_shell.runtime.output_stream import OutputEvent
from agent_shell.workflow_event_output import compile_output


class _PythonOutputProjector:
    def __init__(self, config: dict[str, object], *, workflow: bool = False) -> None:
        self._config = config
        self._workflow = workflow
        outputs = config.get("event_outputs")
        self._settings = outputs if isinstance(outputs, dict) else {}
        self._renderers = {
            str(name): compile_output(str(setting.get("output_source") or ""))
            for name, setting in self._settings.items()
            if isinstance(setting, dict) and setting.get("enabled") is True
        }

    def _key(self, event: OutputEvent) -> str:
        return event.workflow_event_kind if self._workflow else event.event_type

    def enabled(self, event: OutputEvent) -> bool:
        return self._key(event) in self._renderers

    def render(self, event: OutputEvent) -> str:
        renderer = self._renderers.get(self._key(event))
        if renderer is None:
            return ""
        return renderer(event.output_dict())


class OutputProjector(_PythonOutputProjector):
    """Render stable Agent events through user Python."""


class WorkflowOutputProjector:
    """Route Agent node policies and Workflow-owned non-Agent event scripts."""

    def __init__(
        self,
        configs_by_node: Mapping[str, dict[str, object]],
        *,
        workflow_output_config: dict[str, object] | None = None,
    ) -> None:
        self._projectors = {
            node_id: OutputProjector(config)
            for node_id, config in configs_by_node.items()
        }
        self._workflow_projector = (
            _PythonOutputProjector(workflow_output_config, workflow=True)
            if workflow_output_config is not None
            else None
        )

    def _for(self, event: OutputEvent) -> _PythonOutputProjector | None:
        if event.source_type in {"agent", "subagent"}:
            if not event.workflow_node_id:
                return None
            return self._projectors.get(event.workflow_node_id)
        return self._workflow_projector

    def enabled(self, event: OutputEvent) -> bool:
        projector = self._for(event)
        return projector.enabled(event) if projector is not None else False

    def render(self, event: OutputEvent) -> str:
        projector = self._for(event)
        return projector.render(event) if projector is not None else ""

__all__ = ["OutputProjector", "WorkflowOutputProjector"]
