from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path, PurePosixPath
from string import Formatter
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from agent_shell.capability_manifest import (
    CAPABILITY_BY_TYPE,
    CAPABILITY_MANIFESTS,
    PUBLIC_CAPABILITY_MANIFESTS,
    validate_capability_manifests,
)
from agent_shell.model_provider_contracts import validate_provider_settings
from agent_shell.provider_integrations import bundled_provider_ids
from agent_shell.registries.custom_middlewares import (
    MAX_MIDDLEWARE_SOURCE_LENGTH,
    validate_middleware_source,
)
from agent_shell.registries.custom_tools import (
    CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH,
    CUSTOM_TOOL_RESOURCE_NAME_PATTERN,
)
from agent_shell.registries.skills import SKILL_NAME_MAX_LENGTH, skill_name_issue


SKILL_PROMPT_FIELDS = (
    "skills_locations",
    "skills_load_warnings",
    "skills_list",
)
TASK_DESCRIPTION_FIELDS = ("available_agents",)
PROMPT_PRESET_TEMPLATE_FIELDS = (
    "agent_name",
    "available_workers",
    "worker_name",
    "task",
    "workspace",
)


BlockName = Annotated[str, Field(min_length=1, max_length=120)]
Identifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH,
        pattern=CUSTOM_TOOL_RESOURCE_NAME_PATTERN,
    ),
]
SkillName = Annotated[
    str,
    Field(min_length=1, max_length=SKILL_NAME_MAX_LENGTH),
]
LocalPath = Annotated[str, Field(max_length=4096)]
VirtualPath = Annotated[str, Field(min_length=1, max_length=4096)]
DescriptionDraft = Annotated[str, Field(max_length=100_000)]
PromptOverrideText = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(max_length=100_000),
]
OutputTemplateText = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(max_length=100_000),
]
OutputFilterField = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$",
    ),
    Field(min_length=1, max_length=240),
]
OutputFilterValue = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(min_length=1, max_length=4096),
]
ModelBoolean = Annotated[bool, Field(strict=True)]
ModelText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
    Field(max_length=120),
]
BlockReference = Annotated[str, Field(max_length=120)]
RequiredReference = Annotated[str, Field(min_length=1, max_length=120)]
# Keep user-authored filesystem targets out of upstream framework namespaces.
# Agent Shell enforces this input boundary but does not manage those directories.
RESERVED_VIRTUAL_NAMESPACES = (
    "/large_tool_results/",
    "/conversation_history/",
    "/skills/",
    "/memory/",
    "/memories/",
)


def _validate_format_template(
    value: str,
    *,
    allowed_fields: tuple[str, ...],
    label: str,
    required_fields: tuple[str, ...] | None = None,
) -> str:
    seen: set[str] = set()
    try:
        parsed = Formatter().parse(value)
        for _literal, field_name, format_spec, conversion in parsed:
            if field_name is None:
                continue
            if field_name not in allowed_fields:
                raise ValueError(
                    f"{label} contains an unsupported placeholder: {{{field_name}}}"
                )
            if format_spec or conversion:
                raise ValueError(
                    f"{label} placeholders do not support format specifications or conversions: {{{field_name}}}"
                )
            seen.add(field_name)
        index = 0
        while index < len(value):
            if value[index : index + 2] in {"{{", "}}"}:
                index += 2
                continue
            if value[index] != "{":
                index += 1
                continue
            end = value.find("}", index + 1)
            expression = value[index + 1 : end]
            if expression not in allowed_fields:
                raise ValueError(
                    f"{label} accepts only complete placeholders: {{{expression}}}"
                )
            index = end + 1
    except ValueError as exc:
        if str(exc).startswith(label):
            raise
        raise ValueError(
            f"{label} contains invalid braces; literal braces must be written as {{{{ and }}}}"
        ) from None

    required = allowed_fields if required_fields is None else required_fields
    missing = [field for field in required if field not in seen]
    if missing:
        raise ValueError(
            f"{label} is missing required placeholders: "
            + ", ".join(f"{{{field}}}" for field in missing)
        )
    return value


def _validate_virtual_path(value: str) -> str:
    value = value.replace("\\", "/")
    if not value.startswith("/"):
        raise ValueError("virtual path must start with /")
    if any(part == ".." for part in value.split("/")):
        raise ValueError("virtual path must not contain ..")
    normalized = posixpath.normpath(value)
    return "/" + normalized.lstrip("/")


def _validate_virtual_directory_path(value: str) -> str:
    if not value.replace("\\", "/").endswith("/"):
        raise ValueError("virtual directory path must end with /")
    normalized = _validate_virtual_path(value)
    return "/" if normalized == "/" else normalized.rstrip("/") + "/"


def _validate_virtual_file_path(value: str) -> str:
    if value.replace("\\", "/").endswith("/"):
        raise ValueError("virtual file path must not end with /")
    normalized = _validate_virtual_path(value)
    if normalized == "/":
        raise ValueError("virtual file path must include a file name")
    return normalized


def _validate_local_path(value: str) -> str:
    if value and not Path(value).is_absolute():
        raise ValueError("local path must be absolute")
    return value


def _validate_required_local_path(value: str) -> str:
    if not value:
        raise ValueError("local path must not be empty")
    return _validate_local_path(value)


def _reserved_virtual_namespace(path: str, *, is_directory: bool) -> str | None:
    for namespace in RESERVED_VIRTUAL_NAMESPACES:
        if path.startswith(namespace):
            return namespace
        if is_directory and namespace.startswith(path):
            return namespace
        if not is_directory and path == namespace.rstrip("/"):
            return namespace
    return None


class StrictBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BlockName


CredentialValue = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(min_length=1, max_length=4096),
]
CREDENTIAL_VALUE_ADAPTER = TypeAdapter(CredentialValue | None)


def _reject_masked_credential(value: str | None) -> str | None:
    if value is not None and len(value) >= 4 and set(value) <= {"*", "•"}:
        raise ValueError("masked secret text cannot replace a credential")
    return value


class ModelBlock(StrictBlock):
    provider: Annotated[
        str,
        Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$"),
    ]
    base_url: Annotated[str, Field(min_length=1, max_length=2048)]
    credential: CredentialValue | None
    model: Annotated[str, Field(min_length=1, max_length=240)]
    provider_settings: dict[str, JsonValue]
    tool_choice: ModelText | ModelBoolean | dict[str, JsonValue] | None
    response_format: dict[str, JsonValue] | None
    model_settings: dict[str, JsonValue]

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        if value not in bundled_provider_ids():
            raise ValueError(
                "provider must be bundled with this Agent Shell version"
            )
        return value

    @model_validator(mode="after")
    def validate_settings_for_provider(self) -> ModelBlock:
        if self.provider == "google_vertexai" and self.credential is not None:
            raise ValueError(
                "google_vertexai uses Application Default Credentials"
            )
        self.provider_settings = validate_provider_settings(
            self.provider,
            self.provider_settings,
        )
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) URL")
        return value.rstrip("/")

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: str | None) -> str | None:
        return _reject_masked_credential(value)

    @field_validator("model_settings")
    @classmethod
    def validate_model_settings(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        reserved = sorted(set(value) & {"response_format", "tool_choice", "tools"})
        if reserved:
            raise ValueError(
                "model_settings contains dedicated ModelRequest fields: "
                + ", ".join(reserved)
            )
        return value

    @field_validator("response_format")
    @classmethod
    def validate_response_format(
        cls, value: dict[str, JsonValue] | None
    ) -> dict[str, JsonValue] | None:
        if value is None:
            return None
        missing = [
            field
            for field in ("title", "description")
            if not isinstance(value.get(field), str) or not value[field].strip()
        ]
        if missing:
            raise ValueError(
                "response_format JSON Schema requires non-empty: "
                + ", ".join(missing)
            )
        return value

class CustomToolBlock(StrictBlock):
    tools: list[Identifier] = Field(default_factory=list, max_length=200)

    @field_validator("tools")
    @classmethod
    def unique_tools(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class CustomMiddlewareEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BlockName
    enabled: bool = True
    source: Annotated[
        str,
        Field(min_length=1, max_length=MAX_MIDDLEWARE_SOURCE_LENGTH),
    ]

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        validate_middleware_source(value)
        return value


class CustomMiddlewareBlock(StrictBlock):
    middlewares: list[CustomMiddlewareEntry] = Field(
        default_factory=list,
        max_length=100,
    )


OutputEventName = Literal[
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "tool_error",
    "subagent",
    "context_worker",
    "custom",
    "lifecycle",
]
OUTPUT_EVENT_NAMES = (
    "assistant_text",
    "reasoning",
    "tool_call",
    "tool_result",
    "tool_error",
    "subagent",
    "context_worker",
    "custom",
    "lifecycle",
)
OUTPUT_COMMON_TEMPLATE_VARIABLES = (
    "event_type",
    "phase",
    "sequence",
    "timestamp",
    "namespace",
    "agent_name",
    "node",
    "message",
)
OUTPUT_EVENT_TEMPLATE_VARIABLES = {
    "assistant_text": ("message_id",),
    "reasoning": ("message_id",),
    "tool_call": ("tool_name", "tool_call_id", "arguments"),
    "tool_result": ("tool_name", "tool_call_id", "status", "output"),
    "tool_error": ("tool_name", "tool_call_id", "status", "error_code"),
    "subagent": ("subagent_name", "tool_call_id", "status"),
    "context_worker": (
        "worker_name",
        "tool_call_id",
        "status",
        "error_code",
    ),
    "custom": ("channel", "data_json"),
    "lifecycle": ("status", "finish_reason", "error_code"),
}
_OUTPUT_PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")


def _validate_output_template(event_name: str, template: str) -> None:
    placeholders = [item.strip() for item in _OUTPUT_PLACEHOLDER_RE.findall(template)]
    remainder = _OUTPUT_PLACEHOLDER_RE.sub("", template)
    if "{{" in remainder or "}}" in remainder:
        raise PydanticCustomError(
            "output_template_malformed",
            "Output template for {event_name} contains an incomplete placeholder.",
            {"event_name": event_name},
        )
    allowed = frozenset(OUTPUT_COMMON_TEMPLATE_VARIABLES) | frozenset(
        OUTPUT_EVENT_TEMPLATE_VARIABLES[event_name]
    )
    unknown = sorted(set(placeholders) - allowed)
    if unknown:
        raise PydanticCustomError(
            "output_template_unknown_variables",
            "Output template for {event_name} contains unsupported variables: {variables}.",
            {"event_name": event_name, "variables": ", ".join(unknown)},
        )


class OutputEventTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    enabled: bool
    template: OutputTemplateText


class OutputFilterMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    field: OutputFilterField
    value: OutputFilterValue


class OutputModeBlock(StrictBlock):
    filter_mode: Literal["allowlist", "blocklist"]
    filter_mappings: Annotated[list[OutputFilterMapping], Field(max_length=100)]
    variable_encoding: Literal["html", "plain"]
    event_templates: dict[OutputEventName, OutputEventTemplate]

    @model_validator(mode="after")
    def validate_output_mode(self) -> "OutputModeBlock":
        expected = set(OUTPUT_EVENT_NAMES)
        actual = set(self.event_templates)
        if actual != expected:
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            details = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unexpected:
                details.append("unexpected=" + ",".join(unexpected))
            raise PydanticCustomError(
                "output_event_types_invalid",
                "Output event templates do not match the current event types: {details}.",
                {"details": " ".join(details)},
            )
        for event_name in OUTPUT_EVENT_NAMES:
            setting = self.event_templates[event_name]
            if setting.enabled and not setting.template:
                raise PydanticCustomError(
                    "output_template_empty",
                    "Enabled output template for {event_name} must not be empty.",
                    {"event_name": event_name},
                )
            _validate_output_template(event_name, setting.template)
        return self


ExceptionRetryStrategy = Literal["provider_native", "model_retry_middleware"]
EXCEPTION_RETRY_STRATEGIES = (
    "provider_native",
    "model_retry_middleware",
)
ExceptionRetryCondition = Literal[
    "transport_error",
    "timeout",
    "rate_limit",
    "server_error",
    "authentication_error",
]
EXCEPTION_RETRY_CONDITIONS = (
    "transport_error",
    "timeout",
    "rate_limit",
    "server_error",
    "authentication_error",
)
DEFAULT_EXCEPTION_RETRY_CONDITIONS = (
    "transport_error",
    "timeout",
    "rate_limit",
    "server_error",
)


class ExceptionRetryBlock(StrictBlock):
    strategy: ExceptionRetryStrategy = "provider_native"
    force_non_streaming: bool = False
    max_retries: Annotated[int, Field(strict=True, ge=0, le=10)] = 2
    retry_on: list[ExceptionRetryCondition] = Field(
        default_factory=lambda: list(DEFAULT_EXCEPTION_RETRY_CONDITIONS),
        max_length=len(EXCEPTION_RETRY_CONDITIONS),
    )

    @field_validator("retry_on")
    @classmethod
    def unique_retry_conditions(
        cls, values: list[ExceptionRetryCondition]
    ) -> list[ExceptionRetryCondition]:
        if len(values) != len(set(values)):
            raise ValueError("retry_on conditions must be unique")
        return values


class SystemPromptBlock(StrictBlock):
    system_prompt: Annotated[str, Field(min_length=1, max_length=200_000)]


class VirtualDirectorySource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    virtual_path: VirtualPath
    source_path: LocalPath

    _virtual_path = field_validator("virtual_path")(_validate_virtual_directory_path)
    _source_path = field_validator("source_path")(_validate_required_local_path)


class MappedDirectory(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    virtual_path: VirtualPath
    local_path: LocalPath

    _virtual_path = field_validator("virtual_path")(_validate_virtual_directory_path)
    _local_path = field_validator("local_path")(_validate_required_local_path)


class VirtualFileSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    virtual_path: VirtualPath
    source_path: LocalPath

    _virtual_path = field_validator("virtual_path")(_validate_virtual_file_path)
    _source_path = field_validator("source_path")(_validate_required_local_path)


class FilesystemToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool = True
    description_override: PromptOverrideText | None = None


class RequiredFilesystemToolConfig(FilesystemToolConfig):
    visible: Literal[True] = True


class OptionalFilesystemToolConfig(FilesystemToolConfig):
    visible: bool = False


class ExecuteFilesystemToolConfig(FilesystemToolConfig):
    visible: Literal[False] = False


class FilesystemToolConfigs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ls: FilesystemToolConfig = Field(default_factory=FilesystemToolConfig)
    read_file: RequiredFilesystemToolConfig = Field(
        default_factory=RequiredFilesystemToolConfig
    )
    write_file: FilesystemToolConfig = Field(default_factory=FilesystemToolConfig)
    edit_file: FilesystemToolConfig = Field(default_factory=FilesystemToolConfig)
    delete: OptionalFilesystemToolConfig = Field(
        default_factory=OptionalFilesystemToolConfig
    )
    glob: FilesystemToolConfig = Field(default_factory=FilesystemToolConfig)
    grep: FilesystemToolConfig = Field(default_factory=FilesystemToolConfig)
    execute: ExecuteFilesystemToolConfig = Field(
        default_factory=ExecuteFilesystemToolConfig
    )


class FilesystemBlock(StrictBlock):
    mapped_directories: list[MappedDirectory] = Field(default_factory=list, max_length=100)
    virtual_directories: list[VirtualDirectorySource] = Field(default_factory=list, max_length=100)
    virtual_files: list[VirtualFileSource] = Field(default_factory=list, max_length=100)
    system_prompt_override: PromptOverrideText | None = None
    tool_token_limit_before_evict: Annotated[int, Field(ge=1)] | None = 20_000
    tool_configs: FilesystemToolConfigs = Field(default_factory=FilesystemToolConfigs)

    @model_validator(mode="after")
    def validate_filesystem_paths(self) -> "FilesystemBlock":
        directory_items = [*self.mapped_directories, *self.virtual_directories]
        for item in directory_items:
            namespace = _reserved_virtual_namespace(
                item.virtual_path, is_directory=True
            )
            if namespace is not None:
                raise ValueError(
                    "virtual directory overlaps a reserved system namespace: "
                    f"{item.virtual_path}, {namespace}"
                )
        for item in self.virtual_files:
            namespace = _reserved_virtual_namespace(
                item.virtual_path, is_directory=False
            )
            if namespace is not None:
                raise ValueError(
                    "virtual file uses a reserved system namespace: "
                    f"{item.virtual_path}, {namespace}"
                )

        mapped_paths = [item.virtual_path for item in self.mapped_directories]
        for index, path in enumerate(mapped_paths):
            for other in mapped_paths[index + 1 :]:
                if path.startswith(other) or other.startswith(path):
                    raise ValueError(
                        f"mapped directory routes must not overlap: {path}, {other}"
                    )

        virtual_directory_paths = [item.virtual_path for item in self.virtual_directories]
        if len(virtual_directory_paths) != len(set(virtual_directory_paths)):
            raise ValueError("virtual directory targets must be unique")

        mapped_local_paths: set[str] = set()
        for item in self.mapped_directories:
            local = Path(item.local_path)
            if not local.is_dir():
                raise ValueError(f"mapped local_path must be an existing directory: {local}")
            canonical = os.path.normcase(str(local.resolve()))
            if canonical in mapped_local_paths:
                raise ValueError(f"mapped local directories must be unique: {local}")
            mapped_local_paths.add(canonical)

        for item in self.virtual_directories:
            source = Path(item.source_path)
            if not source.is_dir():
                raise ValueError(
                    f"virtual directory source_path must be an existing directory: {source}"
                )
            for route in mapped_paths:
                if item.virtual_path.startswith(route) or route.startswith(item.virtual_path):
                    raise ValueError(
                        "virtual and mapped directories must not overlap: "
                        f"{item.virtual_path}, {route}"
                    )

        target_origins: dict[str, str] = {}
        directory_origins: dict[str, str] = {}
        for item in self.virtual_directories:
            source = Path(item.source_path)
            directory_key = item.virtual_path.rstrip("/")
            previous_directory = directory_origins.get(directory_key)
            if previous_directory is not None:
                raise ValueError(
                    "virtual directory target conflicts: "
                    f"{item.virtual_path} ({previous_directory}, {source})"
                )
            directory_origins[directory_key] = str(source)
            for filepath in sorted(source.rglob("*")):
                relative = filepath.relative_to(source).as_posix()
                target = f"{item.virtual_path}{relative}"
                if filepath.is_dir():
                    if target in target_origins:
                        raise ValueError(
                            "virtual target cannot be both file and directory: "
                            f"{target}"
                        )
                    previous_directory = directory_origins.get(target)
                    if previous_directory is not None:
                        raise ValueError(
                            "virtual directory target conflicts: "
                            f"{target}/ ({previous_directory}, {filepath})"
                        )
                    directory_origins[target] = str(filepath)
                    continue
                if not filepath.is_file():
                    continue
                if target in directory_origins:
                    raise ValueError(
                        f"virtual target cannot be both file and directory: {target}"
                    )
                previous = target_origins.get(target)
                if previous is not None:
                    raise ValueError(
                        f"virtual file target conflicts: {target} ({previous}, {filepath})"
                    )
                target_origins[target] = str(filepath)

        for item in self.virtual_files:
            source = Path(item.source_path)
            if not source.is_file():
                raise ValueError(
                    f"virtual file source_path must be an existing file: {source}"
                )
            if PurePosixPath(item.virtual_path).name != source.name:
                raise ValueError(
                    "virtual file name must match source file name: "
                    f"{item.virtual_path}, {source.name}"
                )
            for route in mapped_paths:
                if item.virtual_path.startswith(route):
                    raise ValueError(
                        f"virtual file target is hidden by mapped directory: {item.virtual_path}"
                    )
            if item.virtual_path in directory_origins:
                raise ValueError(
                    f"virtual target cannot be both file and directory: {item.virtual_path}"
                )
            previous = target_origins.get(item.virtual_path)
            if previous is not None:
                raise ValueError(
                    "virtual file target conflicts: "
                    f"{item.virtual_path} ({previous}, {source})"
                )
            target_origins[item.virtual_path] = str(source)

        return self


class SkillBlock(StrictBlock):
    skills: list[SkillName] = Field(default_factory=list, max_length=200)
    system_prompt_enabled: bool = True
    instruction_override: PromptOverrideText | None = None

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, values: list[str]) -> list[str]:
        for value in values:
            issue = skill_name_issue(value)
            if issue:
                raise ValueError(issue)
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_system_prompt_override(self) -> "SkillBlock":
        if not self.skills:
            raise ValueError("At least one Skill must be selected")
        prompt = self.instruction_override
        if not self.system_prompt_enabled:
            if prompt is not None:
                raise ValueError(
                    "instruction_override must be null when the Skill system prompt is disabled"
                )
            return self
        if prompt is None:
            return self
        _validate_format_template(
            prompt,
            allowed_fields=SKILL_PROMPT_FIELDS,
            label="Skill instructions",
        )
        return self


class SubagentBlock(StrictBlock):
    instruction_override: PromptOverrideText | None = None
    task_description_override: PromptOverrideText | None = None

    @model_validator(mode="after")
    def validate_overrides(self) -> "SubagentBlock":
        task = self.task_description_override
        if task is not None:
            _validate_format_template(
                task,
                allowed_fields=TASK_DESCRIPTION_FIELDS,
                label="Subagent task description",
            )

        return self


class TodoListBlock(StrictBlock):
    system_prompt_override: PromptOverrideText | None = None
    tool_description_override: PromptOverrideText | None = None


PromptPresetTag = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(min_length=1, max_length=4096),
]
PromptPresetText = Annotated[
    str,
    StringConstraints(strip_whitespace=False),
    Field(max_length=100_000),
]
PromptPresetMessageName = Annotated[
    str,
    StringConstraints(strip_whitespace=True),
    Field(min_length=1, max_length=120),
]


class PromptTagReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    tag: PromptPresetTag
    replacement: PromptPresetText = ""

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tag must contain at least one visible character")
        if "\n" in value or "\r" in value:
            raise ValueError("tag must be a single line")
        return value


class PromptStartupMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    role: Literal["user", "assistant"]
    content_template: Annotated[
        str,
        StringConstraints(strip_whitespace=False),
        Field(min_length=1, max_length=100_000),
    ]
    name: PromptPresetMessageName | None = None

    @field_validator("content_template")
    @classmethod
    def validate_content_template(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("startup message content must contain visible text")
        return _validate_format_template(
            value,
            allowed_fields=PROMPT_PRESET_TEMPLATE_FIELDS,
            required_fields=(),
            label="Prompt Preset startup message",
        )


class PromptPresetBlock(StrictBlock):
    tag_replacements: list[PromptTagReplacement] = Field(
        default_factory=list, max_length=100
    )
    startup_messages: list[PromptStartupMessage] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def validate_preset(self) -> "PromptPresetBlock":
        if not self.tag_replacements and not self.startup_messages:
            raise ValueError(
                "Prompt Preset requires at least one tag replacement or startup message"
            )
        tags = [item.tag for item in self.tag_replacements]
        if len(tags) != len(set(tags)):
            raise ValueError("Prompt Preset tags must be unique")
        for index, left in enumerate(tags):
            for right in tags[index + 1 :]:
                if left in right or right in left:
                    raise ValueError(
                        "Prompt Preset tags must not contain or overlap each other"
                    )
        return self


class WorkerDelegationBlock(StrictBlock):
    tool_description: Annotated[str, Field(min_length=1, max_length=100_000)] = (
        "Delegate one self-contained task to a configured Context Worker and return "
        "its final result."
    )
    worker_parameter_description: Annotated[
        str, Field(min_length=1, max_length=10_000)
    ] = "The configured Context Worker that should perform the task."
    task_parameter_description: Annotated[
        str, Field(min_length=1, max_length=10_000)
    ] = "A complete and specific task for the selected Context Worker."
    max_worker_calls_per_request: int = Field(default=16, ge=1, le=64)
    max_parallel_workers: int = Field(default=4, ge=1, le=16)

    @model_validator(mode="after")
    def validate_limits(self) -> "WorkerDelegationBlock":
        for field_name in (
            "tool_description",
            "worker_parameter_description",
            "task_parameter_description",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must contain visible text")
        if self.max_parallel_workers > self.max_worker_calls_per_request:
            raise ValueError(
                "max_parallel_workers must not exceed max_worker_calls_per_request"
            )
        return self


class SubagentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(max_length=120)] = ""
    description: DescriptionDraft = ""
    subagent_override_id: BlockReference = ""


class WorkerBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(max_length=120)] = ""
    description: DescriptionDraft = ""
    worker_profile_id: BlockReference = ""


class CapabilityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Annotated[str, Field(min_length=1, max_length=120)]
    block_id: RequiredReference

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        manifest = CAPABILITY_BY_TYPE.get(value)
        if manifest is None:
            raise ValueError(f"unknown Primary capability: {value}")
        return value


class PrimaryAgentProfile(StrictBlock):
    capability_refs: list[CapabilityReference] = Field(default_factory=list, max_length=100)
    subagents: list[SubagentBinding] = Field(default_factory=list, max_length=100)
    workers: list[WorkerBinding] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_profile(self) -> "PrimaryAgentProfile":
        capability_types = [item.type for item in self.capability_refs]
        if len(capability_types) != len(set(capability_types)):
            raise ValueError("Primary capability_refs must contain at most one item per type")
        return self


class CapabilityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Annotated[str, Field(min_length=1, max_length=120)]
    mode: Literal["replace", "disabled"]
    block_id: BlockReference = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        manifest = CAPABILITY_BY_TYPE.get(value)
        if manifest is None or not manifest.subagent_overrideable:
            raise ValueError(f"capability is not overrideable by Subagent: {value}")
        return value

    @model_validator(mode="after")
    def validate_replace(self) -> "CapabilityOverride":
        manifest = CAPABILITY_BY_TYPE[self.type]
        if self.mode == "disabled" and manifest.required:
            raise ValueError(f"required capability cannot be disabled: {self.type}")
        if self.mode == "replace" and not self.block_id:
            raise ValueError("replace mode requires block_id")
        if self.mode == "disabled" and self.block_id:
            raise ValueError("disabled mode must not include block_id")
        return self


class SubagentOverrideProfile(StrictBlock):
    capability_overrides: list[CapabilityOverride] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def validate_overrides(self) -> "SubagentOverrideProfile":
        capability_types = [item.type for item in self.capability_overrides]
        if len(capability_types) != len(set(capability_types)):
            raise ValueError(
                "Subagent capability_overrides must contain at most one item per type"
            )
        return self


class WorkerCapabilityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Annotated[str, Field(min_length=1, max_length=120)]
    mode: Literal["replace", "disabled"]
    block_id: BlockReference = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        manifest = CAPABILITY_BY_TYPE.get(value)
        if manifest is None or not manifest.worker_overrideable:
            raise ValueError(f"capability is not overrideable by Context Worker: {value}")
        return value

    @model_validator(mode="after")
    def validate_replace(self) -> "WorkerCapabilityOverride":
        manifest = CAPABILITY_BY_TYPE[self.type]
        if self.mode == "disabled" and manifest.required:
            raise ValueError(f"required capability cannot be disabled: {self.type}")
        if self.mode == "replace" and not self.block_id:
            raise ValueError("replace mode requires block_id")
        if self.mode == "disabled" and self.block_id:
            raise ValueError("disabled mode must not include block_id")
        return self


class WorkerProfile(StrictBlock):
    include_client_messages: bool = True
    capability_overrides: list[WorkerCapabilityOverride] = Field(
        default_factory=list, max_length=100
    )

    @model_validator(mode="after")
    def validate_overrides(self) -> "WorkerProfile":
        capability_types = [item.type for item in self.capability_overrides]
        if len(capability_types) != len(set(capability_types)):
            raise ValueError(
                "Worker capability_overrides must contain at most one item per type"
            )
        return self


BLOCK_MODELS: dict[str, type[StrictBlock]] = {
    "model": ModelBlock,
    "system-prompt": SystemPromptBlock,
    "filesystem": FilesystemBlock,
    "todo-list": TodoListBlock,
    "custom-tool": CustomToolBlock,
    "skill": SkillBlock,
    "custom-middleware": CustomMiddlewareBlock,
    "output-mode": OutputModeBlock,
    "exception-retry": ExceptionRetryBlock,
    "subagent": SubagentBlock,
    "prompt-preset": PromptPresetBlock,
    "worker-delegation": WorkerDelegationBlock,
}

validate_capability_manifests(CAPABILITY_MANIFESTS, BLOCK_MODELS)
BLOCK_CATALOG = PUBLIC_CAPABILITY_MANIFESTS

def validate_block_payload(block_type: str, payload: dict) -> dict:
    model = BLOCK_MODELS[block_type].model_validate(payload)
    return model.model_dump(mode="json")


def validate_provider_credential(payload: object) -> str | None:
    value = CREDENTIAL_VALUE_ADAPTER.validate_python(payload)
    return _reject_masked_credential(value)


def validate_primary_agent_payload(payload: dict) -> dict:
    model = PrimaryAgentProfile.model_validate(payload)
    return model.model_dump(mode="json")


def validate_subagent_override_payload(payload: dict) -> dict:
    model = SubagentOverrideProfile.model_validate(payload)
    return model.model_dump(mode="json")


def validate_worker_profile_payload(payload: dict) -> dict:
    model = WorkerProfile.model_validate(payload)
    return model.model_dump(mode="json")
