from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_shell.runtime.errors import AgentRuntimeError


@dataclass(frozen=True, slots=True)
class PreparedAgentInput:
    messages: list[dict[str, str]]
    matched_tag_count: int
    startup_message_count: int


def prepare_agent_input(
    client_messages: list[dict[str, str]],
    preset: dict[str, Any] | None,
    *,
    variables: dict[str, str],
) -> PreparedAgentInput:
    """Build one fresh Agent input without changing the frozen client messages."""

    messages = [dict(message) for message in client_messages]
    if preset is None:
        return PreparedAgentInput(messages, 0, 0)

    replacements = [
        (str(item["tag"]), str(item["replacement"]))
        for item in preset.get("tag_replacements", [])
    ]
    matches: dict[str, list[tuple[int, int]]] = {tag: [] for tag, _ in replacements}
    for message_index, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        content = message["content"]
        for tag, _replacement in replacements:
            start = 0
            while True:
                offset = content.find(tag, start)
                if offset < 0:
                    break
                matches[tag].append((message_index, offset))
                start = offset + len(tag)

    ambiguous = sorted(tag for tag, offsets in matches.items() if len(offsets) > 1)
    if ambiguous:
        raise AgentRuntimeError(
            "ambiguous_prompt_tag",
            "A configured Prompt Preset tag occurs more than once in the client messages.",
            status_code=422,
        )

    replacements_by_message: dict[int, list[tuple[int, int, str]]] = {}
    replacement_by_tag = dict(replacements)
    for tag, offsets in matches.items():
        if not offsets:
            continue
        message_index, offset = offsets[0]
        replacements_by_message.setdefault(message_index, []).append(
            (offset, offset + len(tag), replacement_by_tag[tag])
        )

    for message_index, spans in replacements_by_message.items():
        original = messages[message_index]["content"]
        parts: list[str] = []
        cursor = 0
        for start, end, replacement in sorted(spans):
            parts.append(original[cursor:start])
            parts.append(replacement)
            cursor = end
        parts.append(original[cursor:])
        messages[message_index]["content"] = "".join(parts)

    startup_messages = preset.get("startup_messages", [])
    for template in startup_messages:
        try:
            content = str(template["content_template"]).format_map(variables)
        except KeyError:
            raise AgentRuntimeError(
                "prompt_preset_variable_unavailable",
                "The selected Prompt Preset uses a variable unavailable to this Agent.",
                status_code=422,
            ) from None
        message = {
            "role": str(template["role"]),
            "content": content,
        }
        name = template.get("name")
        if name is not None:
            message["name"] = str(name)
        messages.append(message)

    return PreparedAgentInput(
        messages=messages,
        matched_tag_count=sum(bool(offsets) for offsets in matches.values()),
        startup_message_count=len(startup_messages),
    )
