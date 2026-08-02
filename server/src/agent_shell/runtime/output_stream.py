from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_shell.runtime.errors import AgentRuntimeError
from agent_shell.runtime.model_response import (
    ModelResponse,
    ModelResponseTracker,
    public_finish_reason,
)
from langchain_core.messages import ToolMessage
from langgraph.types import Command

_SUBAGENT_ERROR_STATUSES = frozenset(
    {"failed", "error", "interrupted", "cancelled", "timeout", "timed_out"}
)


def _json_text(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


def _timestamp(value: object) -> str:
    if isinstance(value, (int, float)):
        try:
            instant = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            pass
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _namespace(value: object) -> str:
    if isinstance(value, (list, tuple)):
        parts = [str(part) for part in value if str(part)]
        return "/".join(parts) if parts else "root"
    return str(value or "root")


def _message_text(message: object) -> str:
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "".join(parts)
    return str(content) if content is not None else ""


def _tool_message_from_result(result: object, tool_call_id: str) -> ToolMessage | None:
    if isinstance(result, ToolMessage):
        return result if str(result.tool_call_id or "") == tool_call_id else None
    if not isinstance(result, Command) or not isinstance(result.update, Mapping):
        return None
    messages = result.update.get("messages")
    if not isinstance(messages, (list, tuple)):
        return None
    for message in messages:
        if (
            isinstance(message, ToolMessage)
            and str(message.tool_call_id or "") == tool_call_id
        ):
            return message
    return None


def _tool_result_text(result: object, tool_call_id: str) -> tuple[str, str]:
    tool_message = _tool_message_from_result(result, tool_call_id)
    if tool_message is not None:
        return _message_text(tool_message), str(tool_message.name or "")
    if isinstance(result, Command):
        return "", ""
    if isinstance(result, str):
        return result, ""
    if isinstance(result, (dict, list, tuple)):
        return _json_text(result), ""
    return _message_text(result), str(getattr(result, "name", "") or "")


@dataclass(frozen=True, slots=True)
class OutputEvent:
    event_type: str
    phase: str
    sequence: int
    timestamp: str
    namespace: str = "root"
    agent_name: str = ""
    node: str = ""
    message: str = ""
    values: dict[str, str] = field(default_factory=dict)
    stream_id: str = ""

    def template_values(self) -> dict[str, str]:
        return {
            "event_type": self.event_type,
            "phase": self.phase,
            "sequence": str(self.sequence),
            "timestamp": self.timestamp,
            "namespace": self.namespace,
            "agent_name": self.agent_name,
            "node": self.node,
            "message": self.message,
            **self.values,
        }


@dataclass(frozen=True, slots=True)
class ModelCallBoundary:
    run_key: str


@dataclass(slots=True)
class _MessageBlock:
    timestamp: str
    namespace: str
    agent_name: str
    node: str
    message_id: str
    block_type: str = ""
    streamed_text: str = ""


class V3EventNormalizer:
    """Convert LangChain v3 envelopes into the product's bounded event set."""

    def __init__(
        self,
        primary_name: str,
        model_response_observers: tuple[Callable[[ModelResponse], None], ...] = (),
    ) -> None:
        self._primary_name = primary_name
        self._sequence = 0
        self._blocks: dict[tuple[str, int], _MessageBlock] = {}
        self._message_ids: dict[str, str] = {}
        self._primary_message_runs: set[str] = set()
        self._primary_ai_runs: dict[str, bool] = {}
        self._responses = ModelResponseTracker(model_response_observers)
        self._tool_names: dict[str, str] = {}
        self._subagent_runs: dict[str, tuple[str, str]] = {}
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    @property
    def primary_message_active(self) -> bool:
        return bool(self._primary_message_runs)

    @property
    def finish_reason(self) -> str:
        return public_finish_reason(self._responses.last_primary_finish_reason)

    @property
    def finish_reason_source(self) -> str | None:
        return self._responses.last_primary_finish_reason_source

    def lifecycle(
        self,
        phase: str,
        *,
        status: str,
        finish_reason: str = "",
        error_code: str = "",
    ) -> OutputEvent:
        return self._event(
            "lifecycle",
            phase,
            timestamp=_timestamp(None),
            message=status,
            status=status,
            finish_reason=finish_reason,
            error_code=error_code,
        )

    def feed(self, envelope: object) -> list[OutputEvent | ModelCallBoundary]:
        if not isinstance(envelope, dict):
            return []
        method = str(envelope.get("method") or "")
        params = envelope.get("params")
        if not isinstance(params, dict):
            return []
        timestamp = _timestamp(params.get("timestamp"))
        namespace = _namespace(params.get("namespace"))
        data = params.get("data")
        if method == "messages":
            return self._message_events(
                data, timestamp=timestamp, namespace=namespace
            )
        if method == "tools":
            return self._tool_events(data, timestamp=timestamp, namespace=namespace)
        if method == "custom" or method.startswith("custom:"):
            serialized = _json_text(data)
            channel = method.partition(":")[2] or "custom"
            return [
                self._event(
                    "custom",
                    "end",
                    timestamp=timestamp,
                    namespace=namespace,
                    message=serialized,
                    channel=channel,
                    data_json=serialized,
                )
            ]
        if method == "lifecycle" and isinstance(data, dict):
            status = str(data.get("event") or "running")
            lifecycle_namespace = _namespace(data.get("namespace"))
            if status == "started":
                subagent_name = str(data.get("graph_name") or "")
                if not subagent_name:
                    return []
                cause = data.get("cause")
                tool_call_id = (
                    str(cause.get("tool_call_id") or "")
                    if isinstance(cause, dict)
                    else ""
                )
                self._subagent_runs[lifecycle_namespace] = (
                    subagent_name,
                    tool_call_id,
                )
                phase = "start"
            else:
                subagent = self._subagent_runs.pop(lifecycle_namespace, None)
                if subagent is None:
                    return []
                subagent_name, tool_call_id = subagent
                phase = "error" if status in _SUBAGENT_ERROR_STATUSES else "end"
            values = {
                "status": status,
                "tool_call_id": tool_call_id,
                "subagent_name": subagent_name,
            }
            return [
                self._event(
                    "subagent",
                    phase,
                    timestamp=timestamp,
                    namespace=lifecycle_namespace,
                    message=status,
                    **values,
                )
            ]
        # These methods contain state, task inputs/results, checkpoints, HITL
        # payloads, or debug data and are never exposed as template variables.
        if method in {
            "values",
            "updates",
            "tasks",
            "checkpoints",
            "input",
            "input.requested",
            "debug",
        }:
            return []
        return []

    def _message_events(
        self, data: object, *, timestamp: str, namespace: str
    ) -> list[OutputEvent | ModelCallBoundary]:
        if not isinstance(data, (list, tuple)) or len(data) != 2:
            return []
        payload, raw_metadata = data
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        node = str(metadata.get("langgraph_node") or "")
        agent_name = str(metadata.get("lc_agent_name") or self._primary_name)
        run_id = str(metadata.get("run_id") or "")
        run_key = run_id or f"{namespace}:{agent_name}"
        is_primary = agent_name == self._primary_name and namespace == "root"

        if not isinstance(payload, dict):
            if not is_primary:
                return []
            usage = getattr(payload, "usage_metadata", None)
            response_metadata = getattr(payload, "response_metadata", None)
            additional_kwargs = getattr(payload, "additional_kwargs", None)
            usage_data = usage if isinstance(usage, dict) else {}
            metadata_data = (
                response_metadata if isinstance(response_metadata, dict) else {}
            )
            additional_data = (
                additional_kwargs if isinstance(additional_kwargs, dict) else {}
            )
            content_blocks = getattr(payload, "content_blocks", None)
            self._merge_usage(usage_data)
            self._responses.record(
                timestamp=timestamp,
                namespace=namespace,
                agent_name=agent_name,
                node=node,
                run_id=run_id,
                run_key=run_key,
                message_id=str(getattr(payload, "id", "") or ""),
                is_primary=True,
                usage=usage_data,
                response_metadata=metadata_data,
                additional_kwargs=additional_data,
                content_blocks=(
                    [block for block in content_blocks if isinstance(block, dict)]
                    if isinstance(content_blocks, list)
                    else []
                ),
            )
            return [
                ModelCallBoundary(run_key),
                *self._whole_message_events(
                    payload,
                    timestamp=timestamp,
                    namespace=namespace,
                    agent_name=agent_name,
                    node=node,
                ),
            ]

        event_name = str(payload.get("event") or "")
        if event_name == "message-start":
            message_id = str(payload.get("id") or payload.get("message_id") or "")
            self._message_ids[run_key] = message_id
            self._responses.begin(run_key, payload.get("metadata"))
            is_primary_ai = is_primary and str(payload.get("role") or "ai") == "ai"
            self._primary_ai_runs[run_key] = is_primary_ai
            if is_primary_ai:
                self._primary_message_runs.add(run_key)
            return [ModelCallBoundary(run_key)] if is_primary_ai else []
        if event_name == "message-finish":
            usage = payload.get("usage")
            usage_data = usage if isinstance(usage, dict) else {}
            response_metadata = payload.get("metadata")
            metadata_data = (
                response_metadata if isinstance(response_metadata, dict) else {}
            )
            additional_kwargs = payload.get("additional_kwargs")
            additional_data = (
                additional_kwargs if isinstance(additional_kwargs, dict) else {}
            )
            incomplete_block_count = sum(
                1 for key in self._blocks if key[0] == run_key
            )
            if incomplete_block_count:
                diagnostics = self._responses.diagnostics(run_key)
                diagnostics["incomplete_block_count"] = (
                    diagnostics.get("incomplete_block_count", 0)
                    + incomplete_block_count
                )
            self._merge_usage(usage_data)
            is_primary_message = self._primary_ai_runs.get(run_key, is_primary)
            self._responses.record(
                timestamp=timestamp,
                namespace=namespace,
                agent_name=agent_name,
                node=node,
                run_id=run_id,
                run_key=run_key,
                message_id=self._message_ids.get(run_key, ""),
                is_primary=is_primary_message,
                usage=usage_data,
                response_metadata=metadata_data,
                additional_kwargs=additional_data,
            )
            self._discard_message(run_key)
            return []
        if event_name == "error":
            is_primary_message = self._primary_ai_runs.get(run_key, is_primary)
            self._discard_message(run_key)
            if is_primary_message:
                raise AgentRuntimeError(
                    "agent_execution_failed",
                    "The model response stream failed.",
                    status_code=502,
                )
            return []

        if not self._primary_ai_runs.get(run_key, is_primary):
            return []

        index = payload.get("index")
        if not isinstance(index, int):
            return []
        key = (run_key, index)
        message_id = self._message_ids.get(run_key, "")
        if event_name == "content-block-start":
            content = payload.get("content")
            block_type = (
                str(content.get("type") or "") if isinstance(content, dict) else ""
            )
            self._blocks[key] = _MessageBlock(
                timestamp=timestamp,
                namespace=namespace,
                agent_name=agent_name,
                node=node,
                message_id=message_id,
                block_type=block_type,
            )
            diagnostics = self._responses.diagnostics(run_key)
            diagnostics["content_block_count"] = (
                diagnostics.get("content_block_count", 0) + 1
            )
            stream_id = f"{run_key}:{index}"
            if block_type in {"text", "reasoning"}:
                return [
                    self._event(
                        "reasoning"
                        if block_type == "reasoning"
                        else "assistant_text",
                        "start",
                        timestamp=timestamp,
                        namespace=namespace,
                        agent_name=agent_name,
                        node=node,
                        message_id=message_id,
                        stream_id=stream_id,
                    )
                ]
            if block_type in {
                "tool_call",
                "server_tool_call",
                "tool_call_chunk",
                "server_tool_call_chunk",
            } and isinstance(content, dict):
                return [
                    self._tool_call_event(
                        content,
                        phase="start",
                        timestamp=timestamp,
                        namespace=namespace,
                        agent_name=agent_name,
                        node=node,
                        stream_id=stream_id,
                    )
                ]
            return []
        if event_name == "content-block-delta":
            block = self._blocks.get(key)
            delta = payload.get("delta")
            if block is None or not isinstance(delta, dict):
                return []
            fragment = self._block_text(delta)
            if not fragment or block.block_type not in {"text", "reasoning"}:
                return []
            block.streamed_text += fragment
            diagnostics = self._responses.diagnostics(run_key)
            diagnostics["delta_block_count"] = (
                diagnostics.get("delta_block_count", 0) + 1
            )
            return [
                self._event(
                    "reasoning"
                    if block.block_type == "reasoning"
                    else "assistant_text",
                    "delta",
                    timestamp=timestamp,
                    namespace=namespace,
                    agent_name=agent_name,
                    node=node,
                    message=fragment,
                    message_id=message_id,
                    stream_id=f"{run_key}:{index}",
                )
            ]
        if event_name == "content-block-finish":
            content = payload.get("content")
            if not isinstance(content, dict):
                return []
            self._responses.finish_block(run_key, index, content)
            block = self._blocks.pop(
                key,
                _MessageBlock(
                    timestamp=timestamp,
                    namespace=namespace,
                    agent_name=agent_name,
                    node=node,
                    message_id=message_id,
                ),
            )
            block.timestamp = timestamp
            block_type = str(content.get("type") or "")
            if block.block_type in {"text", "reasoning"}:
                diagnostics = self._responses.diagnostics(run_key)
                if block_type == block.block_type:
                    complete_text = self._block_text(content)
                else:
                    complete_text = block.streamed_text
                    diagnostics["block_type_mismatch_count"] = (
                        diagnostics.get("block_type_mismatch_count", 0) + 1
                    )
                if (
                    block_type == block.block_type
                    and block.streamed_text
                    and block.streamed_text != complete_text
                ):
                    diagnostics["snapshot_mismatch_count"] = (
                        diagnostics.get("snapshot_mismatch_count", 0) + 1
                    )
                return [
                    self._event(
                        "reasoning"
                        if block.block_type == "reasoning"
                        else "assistant_text",
                        "end",
                        timestamp=block.timestamp,
                        namespace=block.namespace,
                        agent_name=block.agent_name,
                        node=block.node,
                        message=complete_text,
                        message_id=block.message_id,
                        stream_id=f"{run_key}:{index}",
                    )
                ]
            return self._finished_block_events(
                content, block, stream_id=f"{run_key}:{index}"
            )
        return []

    def _whole_message_events(
        self,
        message: object,
        *,
        timestamp: str,
        namespace: str,
        agent_name: str,
        node: str,
    ) -> list[OutputEvent]:
        message_id = str(getattr(message, "id", "") or "")
        blocks = getattr(message, "content_blocks", None)
        if not isinstance(blocks, list):
            text = _message_text(message)
            blocks = [{"type": "text", "text": text}] if text else []
        events: list[OutputEvent] = []
        for index, content in enumerate(blocks):
            if not isinstance(content, dict):
                continue
            block = _MessageBlock(
                timestamp=timestamp,
                namespace=namespace,
                agent_name=agent_name,
                node=node,
                message_id=message_id,
            )
            events.extend(self._finished_block_events(content, block))
        return events

    def _finished_block_events(
        self,
        content: dict[str, object],
        block: _MessageBlock,
        *,
        stream_id: str = "",
    ) -> list[OutputEvent]:
        block_type = str(content.get("type") or "")
        if block_type in {"text", "reasoning"}:
            return [
                self._event(
                    "reasoning" if block_type == "reasoning" else "assistant_text",
                    "end",
                    timestamp=block.timestamp,
                    namespace=block.namespace,
                    agent_name=block.agent_name,
                    node=block.node,
                    message=self._block_text(content),
                    message_id=block.message_id,
                )
            ]
        if block_type in {"tool_call", "server_tool_call"}:
            return [
                self._tool_call_event(
                    content,
                    phase="end",
                    timestamp=block.timestamp,
                    namespace=block.namespace,
                    agent_name=block.agent_name,
                    node=block.node,
                    stream_id=stream_id,
                )
            ]
        if block_type in {"tool_call_chunk", "server_tool_call_chunk"}:
            return [
                self._event(
                    "tool_error",
                    "error",
                    timestamp=block.timestamp,
                    namespace=block.namespace,
                    agent_name=block.agent_name,
                    node=block.node,
                    message="Tool call arguments did not finish.",
                    tool_name=str(content.get("name") or ""),
                    tool_call_id=str(content.get("id") or ""),
                    status="failed",
                    error_code="invalid_tool_call",
                    stream_id=stream_id,
                )
            ]
        if block_type == "invalid_tool_call":
            return [
                self._event(
                    "tool_error",
                    "error",
                    timestamp=block.timestamp,
                    namespace=block.namespace,
                    agent_name=block.agent_name,
                    node=block.node,
                    message="Invalid tool call arguments.",
                    tool_name=str(content.get("name") or ""),
                    tool_call_id=str(content.get("id") or ""),
                    status="failed",
                    error_code="invalid_tool_call",
                    stream_id=stream_id,
                )
            ]
        if block_type == "server_tool_result":
            call_id = str(content.get("tool_call_id") or "")
            status = str(content.get("status") or "success")
            if status == "error":
                return [
                    self._event(
                        "tool_error",
                        "error",
                        timestamp=block.timestamp,
                        namespace=block.namespace,
                        agent_name=block.agent_name,
                        node=block.node,
                        message="Server tool execution failed.",
                        tool_name=self._tool_names.pop(call_id, ""),
                        tool_call_id=call_id,
                        status="failed",
                        error_code="server_tool_error",
                        stream_id=stream_id,
                    )
                ]
            text, result_name = _tool_result_text(content.get("output"), call_id)
            stored_name = self._tool_names.pop(call_id, "")
            name = result_name or stored_name
            return [
                self._event(
                    "tool_result",
                    "end",
                    timestamp=block.timestamp,
                    namespace=block.namespace,
                    agent_name=block.agent_name,
                    node=block.node,
                    message=text,
                    tool_name=name,
                    tool_call_id=call_id,
                    status="completed",
                    output=text,
                    stream_id=stream_id,
                )
            ]
        return []

    @staticmethod
    def _block_text(content: dict[str, object]) -> str:
        block_type = str(content.get("type") or "")
        field_name = (
            "reasoning" if block_type in {"reasoning", "reasoning-delta"} else "text"
        )
        return str(content.get(field_name) or "")

    def _tool_call_event(
        self,
        tool_call: dict[str, object],
        *,
        phase: str,
        timestamp: str,
        namespace: str,
        agent_name: str,
        node: str,
        stream_id: str = "",
    ) -> OutputEvent:
        name = str(tool_call.get("name") or "")
        call_id = str(tool_call.get("id") or "")
        arguments = tool_call.get("args", "")
        arguments_text = (
            arguments if isinstance(arguments, str) else _json_text(arguments)
        )
        if call_id and name:
            self._tool_names[call_id] = name
        return self._event(
            "tool_call",
            phase,
            timestamp=timestamp,
            namespace=namespace,
            agent_name=agent_name,
            node=node,
            message=arguments_text,
            tool_name=name,
            tool_call_id=call_id,
            arguments=arguments_text,
            stream_id=stream_id,
        )

    def _tool_events(
        self, data: object, *, timestamp: str, namespace: str
    ) -> list[OutputEvent]:
        if not isinstance(data, dict):
            return []
        lifecycle = str(data.get("event") or "")
        call_id = str(data.get("tool_call_id") or "")
        output = data.get("output")
        result_text, result_name = _tool_result_text(output, call_id)
        name = str(
            data.get("tool_name") or result_name or self._tool_names.get(call_id, "")
        )
        if call_id and name:
            self._tool_names[call_id] = name
        if lifecycle == "tool-started":
            return []
        if lifecycle == "tool-output-delta":
            return []
        if lifecycle == "tool-finished":
            self._tool_names.pop(call_id, None)
            return [
                self._event(
                    "tool_result",
                    "end",
                    timestamp=timestamp,
                    namespace=namespace,
                    node="tools",
                    message=result_text,
                    tool_name=name,
                    tool_call_id=call_id,
                    status="completed",
                    output=result_text,
                )
            ]
        if "fail" in lifecycle or "error" in lifecycle:
            self._tool_names.pop(call_id, None)
            return [
                self._event(
                    "tool_error",
                    "error",
                    timestamp=timestamp,
                    namespace=namespace,
                    node="tools",
                    message="Tool execution failed.",
                    tool_name=name,
                    tool_call_id=call_id,
                    status="failed",
                    error_code="tool_execution_failed",
                )
            ]
        return []

    def _discard_message(self, run_key: str) -> None:
        for key in [item for item in self._blocks if item[0] == run_key]:
            self._blocks.pop(key, None)
        self._message_ids.pop(run_key, None)
        self._responses.discard(run_key)
        self._primary_ai_runs.pop(run_key, None)
        self._primary_message_runs.discard(run_key)

    def close_primary_messages(self) -> None:
        """Discard normalization state after the graph stream is exhausted."""

        run_keys = self._primary_message_runs | {key[0] for key in self._blocks}
        for run_key in sorted(run_keys):
            self._discard_message(run_key)

    def abort_primary_messages(self) -> None:
        run_keys = self._primary_message_runs | {key[0] for key in self._blocks}
        for run_key in list(run_keys):
            self._discard_message(run_key)

    def _merge_usage(self, usage: object) -> None:
        if not isinstance(usage, dict):
            return
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                self.usage[key] += value
        output_details = usage.get("output_token_details")
        if isinstance(output_details, dict):
            reasoning = output_details.get("reasoning")
            if isinstance(reasoning, int) and reasoning >= 0:
                self.usage["reasoning_tokens"] = (
                    self.usage.get("reasoning_tokens", 0) + reasoning
                )

    def _event(
        self,
        event_type: str,
        phase: str,
        *,
        timestamp: str,
        namespace: str = "root",
        agent_name: str = "",
        node: str = "",
        message: str = "",
        stream_id: str = "",
        **values: str,
    ) -> OutputEvent:
        self._sequence += 1
        return OutputEvent(
            event_type=event_type,
            phase=phase,
            sequence=self._sequence,
            timestamp=timestamp,
            namespace=namespace,
            agent_name=agent_name or self._primary_name,
            node=node,
            message=message,
            values={key: str(value or "") for key, value in values.items()},
            stream_id=stream_id,
        )


__all__ = ["ModelCallBoundary", "OutputEvent", "V3EventNormalizer"]
