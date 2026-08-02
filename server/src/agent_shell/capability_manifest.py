from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


UNCONFIGURED_FILESYSTEM_TOOL_NAMES = (
    "read_file",
)

FILESYSTEM_TOOL_NAMES = (
    "ls",
    *UNCONFIGURED_FILESYSTEM_TOOL_NAMES,
    "write_file",
    "edit_file",
    "delete",
    "glob",
    "grep",
    "execute",
)


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    """Small catalog record shared by the API and Vue authoring forms."""

    type: str
    terminology_key: str
    label: str
    order: int
    icon_key: str
    editor_key: str
    subagent_overrideable: bool
    required: bool
    subagent_policy: Literal["inherit", "force-remove", "top-level-only"]
    tool_names: tuple[str, ...] = ()

    def public_dict(self) -> dict:
        return {
            "type": self.type,
            "terminology_key": self.terminology_key,
            "label": self.label,
            "order": self.order,
            "icon_key": self.icon_key,
            "editor_key": self.editor_key,
            "subagent_overrideable": self.subagent_overrideable,
            "required": self.required,
            "subagent_policy": self.subagent_policy,
            "tool_names": list(self.tool_names),
        }


CAPABILITY_MANIFESTS = (
    CapabilityManifest(
        "model", "model", "模型", 1, "bot", "model",
        subagent_overrideable=True, required=True, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "system-prompt", "system-prompt", "系统提示词",
        2, "message-square", "system_prompt",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "filesystem", "file-system", "文件系统", 3,
        "folder", "filesystem",
        subagent_overrideable=False, required=False, subagent_policy="inherit",
        tool_names=FILESYSTEM_TOOL_NAMES,
    ),
    CapabilityManifest(
        "todo-list", "todo-list", "待办计划", 4,
        "check", "todo_list",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
        tool_names=("write_todos",),
    ),
    CapabilityManifest(
        "custom-tool", "custom-tool", "自定义工具", 5,
        "wrench", "custom_tool",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "skill", "skill", "技能", 6, "sparkles",
        "skill", subagent_overrideable=True, required=False,
        subagent_policy="inherit",
    ),
    CapabilityManifest(
        "custom-middleware", "middleware", "自定义中间件", 7,
        "layers", "custom_middleware",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "output-mode", "output-policy", "输出模式", 8,
        "braces", "output_mode",
        subagent_overrideable=False, required=True, subagent_policy="top-level-only",
    ),
    CapabilityManifest(
        "exception-retry", "exception-retry", "异常重试", 9,
        "arrow-repeat", "exception_retry",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "prompt-preset", "prompt-preset", "提示词预设", 10,
        "messages-square", "prompt_preset",
        subagent_overrideable=True, required=False, subagent_policy="inherit",
    ),
    CapabilityManifest(
        "subagent", "delegation", "委派能力", 11,
        "users", "subagent",
        subagent_overrideable=False, required=False, subagent_policy="force-remove",
    ),
)


def validate_capability_manifests(
    manifests: tuple[CapabilityManifest, ...],
    block_models: Mapping[str, object] | None = None,
) -> None:
    types = [manifest.type for manifest in manifests]
    orders = [manifest.order for manifest in manifests]
    if len(types) != len(set(types)):
        raise ValueError("capability manifest types must be unique")
    if len(orders) != len(set(orders)) or orders != sorted(orders):
        raise ValueError("capability manifest orders must be unique and ordered")
    if block_models is not None and set(types) != set(block_models):
        raise ValueError("capability manifests and block models must correspond one-to-one")


validate_capability_manifests(CAPABILITY_MANIFESTS)
CAPABILITY_BY_TYPE = {manifest.type: manifest for manifest in CAPABILITY_MANIFESTS}
PUBLIC_CAPABILITY_MANIFESTS = [manifest.public_dict() for manifest in CAPABILITY_MANIFESTS]
