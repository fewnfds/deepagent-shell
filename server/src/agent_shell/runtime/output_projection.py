from __future__ import annotations

import html
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent_shell.runtime.output_stream import OutputEvent

_PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")


@dataclass(frozen=True, slots=True)
class StreamProjection:
    prefix: str
    suffix: str


class OutputProjector:
    """Apply output-mode filtering, encoding, and stateless templates."""

    def __init__(self, config: dict[str, object]) -> None:
        self._config = config
        mappings = config.get("filter_mappings")
        self._filter_mappings = mappings if isinstance(mappings, list) else []

    def enabled(self, event: OutputEvent) -> bool:
        return self._setting(event) is not None

    def stream_projection(self, event: OutputEvent) -> StreamProjection | None:
        setting = self._setting(event)
        if setting is None:
            return None
        template = str(setting.get("template") or "")
        message_fields = [
            match
            for match in _PLACEHOLDER_RE.finditer(template)
            if match.group(1).strip() == "message"
        ]
        can_stream = (
            event.event_type in {"assistant_text", "reasoning"}
            and len(message_fields) == 1
            and not self._filter_mappings
            and self._config.get("filter_mode") == "blocklist"
        )
        if not can_stream:
            return None
        message_field = message_fields[0]
        return StreamProjection(
            prefix=self._render_template(template[: message_field.start()], event),
            suffix=self._render_template(template[message_field.end() :], event),
        )

    def render(self, event: OutputEvent) -> str:
        setting = self._setting(event)
        if setting is None or not self._passes_filter(event):
            return ""
        template = str(setting.get("template") or "")
        return self._render_template(template, event) if template else ""

    def encode_message(self, value: str, event: OutputEvent | None = None) -> str:
        return self._encode_text(value)

    def _setting(self, event: OutputEvent) -> dict[str, object] | None:
        templates = self._config.get("event_templates")
        if not isinstance(templates, dict):
            return None
        setting = templates.get(event.event_type)
        if not isinstance(setting, dict) or setting.get("enabled") is not True:
            return None
        return setting

    def _passes_filter(self, event: OutputEvent) -> bool:
        matched = any(
            self._mapping_matches(event, mapping)
            for mapping in self._filter_mappings
        )
        mode = self._config.get("filter_mode")
        return not (
            (mode == "allowlist" and not matched)
            or (mode == "blocklist" and matched)
        )

    def _render_template(self, template: str, event: OutputEvent) -> str:
        values = event.template_values()

        def replace(match: re.Match[str]) -> str:
            return self._encode_text(values.get(match.group(1).strip(), ""))

        return _PLACEHOLDER_RE.sub(replace, template)

    def _encode_text(self, value: str) -> str:
        return (
            html.escape(value, quote=True)
            if self._config.get("variable_encoding") == "html"
            else value
        )

    @staticmethod
    def _mapping_matches(event: OutputEvent, mapping: object) -> bool:
        if not isinstance(mapping, dict):
            return False
        configured_field = str(mapping.get("field") or "")
        expected_value = str(mapping.get("value") or "")
        event_scope, separator, field_name = configured_field.partition(".")
        if separator:
            if event.event_type != event_scope:
                return False
        else:
            field_name = event_scope
        values = event.template_values()
        return field_name in values and values[field_name] == expected_value


class WorkflowOutputProjector:
    """Route Agent policies and optionally hide the Workflow full-state event."""

    def __init__(
        self,
        configs_by_node: Mapping[str, dict[str, object]],
        *,
        non_agent_filter: Callable[[OutputEvent], bool] | None = None,
    ) -> None:
        self._projectors = {
            node_id: OutputProjector(config)
            for node_id, config in configs_by_node.items()
        }
        self._non_agent_filter = non_agent_filter

    def _for(self, event: OutputEvent) -> OutputProjector | None:
        if event.source_type not in {"agent", "subagent"}:
            return None
        if not event.workflow_node_id:
            return None
        return self._projectors.get(event.workflow_node_id)

    def enabled(self, event: OutputEvent) -> bool:
        projector = self._for(event)
        return (
            projector.enabled(event)
            if projector is not None
            else self._passthrough(event)
        )

    def stream_projection(self, event: OutputEvent) -> StreamProjection | None:
        projector = self._for(event)
        return projector.stream_projection(event) if projector is not None else None

    def render(self, event: OutputEvent) -> str:
        projector = self._for(event)
        if projector is not None:
            return projector.render(event)
        return event.message if self._passthrough(event) else ""

    def encode_message(self, value: str, event: OutputEvent | None = None) -> str:
        if event is None:
            return ""
        projector = self._for(event)
        if projector is not None:
            return projector.encode_message(value, event)
        return value if self._passthrough(event) else ""

    def _passthrough(self, event: OutputEvent) -> bool:
        return (
            event.source_type not in {"agent", "subagent"}
            and (
                self._non_agent_filter is None
                or self._non_agent_filter(event)
            )
        )


__all__ = ["OutputProjector", "StreamProjection", "WorkflowOutputProjector"]
