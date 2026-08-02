from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

from pydantic import ValidationError

from agent_shell.capability_manifest import (
    CAPABILITY_BY_TYPE,
    CAPABILITY_MANIFESTS,
    UNCONFIGURED_FILESYSTEM_TOOL_NAMES,
)
from agent_shell.contracts import (
    BLOCK_MODELS,
    CapabilityReference,
    PrimaryAgentProfile,
    SubagentOverrideProfile,
)
from agent_shell.registries.custom_tools import (
    resolve_custom_tool_file,
    scan_custom_tool_file,
)
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.validation.capability_assembly import (
    CapabilityAssemblySubject,
    FilesystemMode,
    capability_assembly_issues,
)
from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport
from agent_shell.validation.subagent_bindings import subagent_binding_issues


SubagentNodeKey = tuple[str, str, bool]


@dataclass(frozen=True, slots=True)
class ResolvedSubagentEdge:
    binding: dict[str, Any]
    target_key: SubagentNodeKey


@dataclass(frozen=True, slots=True)
class ResolvedSubagent:
    key: SubagentNodeKey
    name: str
    include_client_messages: bool
    references: dict[str, str]
    blocks: dict[str, dict[str, Any]]
    filesystem_mode: FilesystemMode
    subagents: tuple[ResolvedSubagentEdge, ...]


@dataclass(frozen=True, slots=True)
class StaticAssembly:
    primary: dict[str, Any]
    references: dict[str, str]
    blocks: dict[str, dict[str, Any]]
    filesystem_mode: FilesystemMode
    subagents: tuple[ResolvedSubagentEdge, ...]
    subagent_nodes: dict[SubagentNodeKey, ResolvedSubagent]


_PRIMARY_REQUIRED_CAPABILITY_TYPES = frozenset(
    manifest.type for manifest in CAPABILITY_MANIFESTS if manifest.required
)
_SUBAGENT_REQUIRED_CAPABILITY_TYPES = frozenset(
    manifest.type
    for manifest in CAPABILITY_MANIFESTS
    if manifest.required and manifest.subagent_policy == "inherit"
)
class ConfigurationValidationService:
    def __init__(
        self,
        blocks: BlockStore,
        agent_configs: AgentConfigStore,
        *,
        custom_tools_dir: Path,
    ) -> None:
        self._blocks = blocks
        self._agent_configs = agent_configs
        self._custom_tools_dir = custom_tools_dir

    def validate_primary(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
        stored: bool = False,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        override_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[ValidationReport, dict[str, Any] | None, StaticAssembly | None]:
        owner_name = str(payload.get("name", ""))
        try:
            model = PrimaryAgentProfile.model_validate(
                (
                    {key: value for key, value in payload.items() if key != "id"}
                    if stored
                    else payload
                )
            )
        except ValidationError as exc:
            contract_report = report_from_validation_error(
                exc,
                stage=stage,
                scope="primary",
                owner_id=owner_id,
                owner_name=owner_name,
            )
            reference_issues = self._reference_issues_from_invalid_primary(
                payload,
                owner_id=owner_id,
                owner_name=owner_name,
                block_overrides=block_overrides,
            )
            return (
                ValidationReport(
                    stage=stage,
                    issues=contract_report.issues + tuple(reference_issues),
                ),
                None,
                None,
            )
        primary = model.model_dump(mode="json")
        report, assembly = self._assemble_primary(
            primary,
            stage=stage,
            owner_id=owner_id,
            block_overrides=block_overrides,
            override_overrides=override_overrides,
        )
        return report, primary, assembly

    def validate_block(
        self,
        block_type: str,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
    ) -> tuple[ValidationReport, dict[str, Any] | None]:
        model = BLOCK_MODELS[block_type]
        try:
            validated_model = model.model_validate(payload)
        except ValidationError as exc:
            return (
                report_from_validation_error(
                    exc,
                    stage=stage,
                    scope="block",
                    owner_id=owner_id,
                    owner_name=str(payload.get("name", "")),
                    owner_type=block_type,
                ),
                None,
            )
        validated = validated_model.model_dump(mode="json")
        if not owner_id:
            return ValidationReport(stage=stage), validated
        current = self._blocks.get_block_internal(block_type, owner_id)
        if current is None:
            return ValidationReport(stage=stage), validated
        prospective = dict(validated)
        prospective["id"] = owner_id
        issues = self._impact_issues_for_block(
            block_type,
            owner_id,
            prospective,
            stage=stage,
        )
        return ValidationReport(stage=stage, issues=tuple(issues)), validated

    def validate_block_copy(
        self,
        block_type: str,
        source: dict[str, Any],
        *,
        name: str,
        stage: str = "block_copy",
    ) -> ValidationReport:
        payload, storage_issue = self._stored_block_payload(block_type, source)
        payload["name"] = name
        if storage_issue is not None:
            return ValidationReport(stage=stage, issues=(storage_issue,))
        try:
            BLOCK_MODELS[block_type].model_validate(payload)
        except ValidationError as exc:
            return report_from_validation_error(
                exc,
                stage=stage,
                scope="block",
                owner_id=str(source.get("id", "")),
                owner_name=name,
                owner_type=block_type,
            )
        return ValidationReport(stage=stage)

    def validate_stored_block(
        self,
        block_type: str,
        block: dict[str, Any],
        *,
        stage: str,
    ) -> ValidationReport:
        payload, storage_issue = self._stored_block_payload(block_type, block)
        if storage_issue is not None:
            return ValidationReport(stage=stage, issues=(storage_issue,))
        try:
            BLOCK_MODELS[block_type].model_validate(payload)
        except ValidationError as exc:
            return report_from_validation_error(
                exc,
                stage=stage,
                scope="block",
                owner_id=str(block.get("id", "")),
                owner_name=str(block.get("name", "")),
                owner_type=block_type,
            )
        return ValidationReport(stage=stage)

    def validate_override(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
        stored: bool = False,
    ) -> tuple[ValidationReport, dict[str, Any] | None]:
        try:
            model = SubagentOverrideProfile.model_validate(
                (
                    {key: value for key, value in payload.items() if key != "id"}
                    if stored
                    else payload
                )
            )
        except ValidationError as exc:
            return (
                report_from_validation_error(
                    exc,
                    stage=stage,
                    scope="subagent_override",
                    owner_id=owner_id,
                    owner_name=str(payload.get("name", "")),
                ),
                None,
            )
        validated = model.model_dump(mode="json")
        references = {
            item["type"]: item["block_id"]
            for item in validated["capability_overrides"]
            if item["mode"] == "replace"
        }
        _, issues = self._load_references(
            references,
            scope="subagent_override",
            owner_id=owner_id,
            owner_name=validated["name"],
            path_prefix="capability_overrides",
        )
        issues.extend(
            subagent_binding_issues(
                list(validated.get("subagents", [])),
                owner_id=owner_id,
                owner_name=validated["name"],
            )
        )
        for binding in validated.get("subagents", []):
            target_id = str(binding.get("subagent_override_id", ""))
            if not target_id or target_id == owner_id:
                continue
            _, target_issue = self._subagent_override(
                target_id,
                binding=binding,
                owner_id=owner_id,
            )
            if target_issue is not None:
                issues.append(target_issue)
        if owner_id and not issues:
            prospective = dict(validated)
            prospective["id"] = owner_id
            issues.extend(
                self._impact_issues_for_override(
                    owner_id,
                    prospective,
                    stage=stage,
                )
            )
        return ValidationReport(stage=stage, issues=tuple(issues)), validated

    def resolve_primary(
        self, primary_id: str, *, stage: str = "request_prepare"
    ) -> tuple[ValidationReport, StaticAssembly | None]:
        primary = self._agent_configs.get_item("primary_agents", primary_id)
        if primary is None:
            issue = ValidationIssue(
                code="assembly.primary_not_found",
                scope="primary",
                owner_id=primary_id,
                path="id",
                message="The requested Primary Agent does not exist.",
                message_key="validation.issue.assembly.primaryNotFound",
                message_args={},
            )
            return ValidationReport(stage=stage, issues=(issue,)), None
        report, _, assembly = self.validate_primary(
            primary,
            stage=stage,
            owner_id=primary_id,
            stored=True,
        )
        return report, assembly

    def validate_repository(self) -> ValidationReport:
        stage = "repository_load"
        issues: list[ValidationIssue] = []
        for block in self._blocks.list_block_headers():
            block_type = block["block_type"]
            if block_type not in BLOCK_MODELS:
                issues.append(
                    ValidationIssue(
                        code="storage.unknown_block_type",
                        scope="block",
                        owner_id=block["id"],
                        owner_name=block["name"],
                        owner_type=block_type,
                        path="block_type",
                        message=(
                            f"Stored configuration type {block_type!r} is not "
                            "supported."
                        ),
                        message_key="errors.unknownConfigurationType",
                        message_args={"type": block_type},
                    )
                )
        for block_type in BLOCK_MODELS:
            for block in self._blocks.list_blocks_internal(block_type):
                issues.extend(
                    self.validate_stored_block(
                        block_type,
                        block,
                        stage=stage,
                    ).issues
                )
        for override in self._agent_configs.list_items("subagent_overrides"):
            report, _ = self.validate_override(
                override,
                stage=stage,
                owner_id=str(override.get("id", "")),
                stored=True,
            )
            issues.extend(report.issues)
        issues.extend(self._saved_primary_issues(stage))
        return ValidationReport(stage=stage, issues=tuple(issues))

    def validate_api_start(self) -> ValidationReport:
        repository = self.validate_repository()
        return ValidationReport(
            stage="api_start",
            issues=repository.issues,
        )

    def _saved_primary_issues(self, stage: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for primary in self._agent_configs.list_items("primary_agents"):
            report, _, _ = self.validate_primary(
                primary,
                stage=stage,
                owner_id=str(primary.get("id", "")),
                stored=True,
            )
            issues.extend(report.issues)
        return issues

    @staticmethod
    def _reference_map(profile: dict[str, Any]) -> dict[str, str]:
        return {
            str(item["type"]): str(item["block_id"])
            for item in profile.get("capability_refs", [])
        }

    def _reference_issues_from_invalid_primary(
        self,
        payload: dict[str, Any],
        *,
        owner_id: str,
        owner_name: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> list[ValidationIssue]:
        references: dict[str, str] = {}
        items = payload.get("capability_refs", [])
        if not isinstance(items, list):
            return []
        for item in items:
            try:
                reference = CapabilityReference.model_validate(item)
            except ValidationError:
                continue
            references[reference.type] = reference.block_id
        _, issues = self._load_references(
            references,
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
            block_overrides=block_overrides,
        )
        return issues

    @staticmethod
    def _stored_block_payload(
        capability_type: str, block: dict[str, Any]
    ) -> tuple[dict[str, Any], ValidationIssue | None]:
        payload = {key: value for key, value in block.items() if key != "id"}
        if capability_type != "model":
            return payload, None
        credential = payload.get("credential")
        if credential is None:
            return payload, None
        if (
            isinstance(credential, dict)
            and set(credential) == {"reference"}
            and isinstance(credential["reference"], str)
            and credential["reference"]
        ):
            payload["credential"] = None
            return payload, None
        return payload, ValidationIssue(
            code="storage.credential_metadata_invalid",
            scope="block",
            owner_id=str(block.get("id", "")),
            owner_name=str(block.get("name", "")),
            owner_type=capability_type,
            path="credential",
            message=(
                "The stored model credential metadata is invalid. "
                "Save the model configuration again."
            ),
            message_key="validation.issue.storage.credentialMetadataInvalid",
            message_args={},
        )

    def _block_contract_issue(
        self,
        capability_type: str,
        block: dict[str, Any],
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        path: str,
        stored: bool = True,
    ) -> ValidationIssue | None:
        if stored:
            payload, storage_issue = self._stored_block_payload(capability_type, block)
        else:
            payload = {key: value for key, value in block.items() if key != "id"}
            storage_issue = None
        if storage_issue is not None:
            detail = storage_issue.message
        else:
            try:
                BLOCK_MODELS[capability_type].model_validate(payload)
                return None
            except (ValidationError, KeyError) as exc:
                if isinstance(exc, ValidationError):
                    report = report_from_validation_error(
                        exc,
                        stage="referenced_block",
                        scope="block",
                        owner_id=str(block.get("id", "")),
                        owner_name=str(block.get("name", "")),
                        owner_type=capability_type,
                    )
                    detail = (
                        report.issues[0].message
                        if report.issues
                        else "The configuration structure is invalid."
                    )
                else:
                    detail = "The configuration type is not supported."
        block_name = str(block.get("name", "")) or "Unnamed configuration"
        return ValidationIssue(
            code="assembly.referenced_block_invalid",
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
            path=path,
            message=(
                f"Referenced {capability_type} configuration {block_name!r} "
                f"does not satisfy the current contract: {detail}"
            ),
            message_key="validation.issue.assembly.referencedBlockInvalid",
            message_args={
                "capability_type": capability_type,
                "block_name": block_name,
                "detail": detail,
            },
        )

    def _load_references(
        self,
        references: dict[str, str],
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        path_prefix: str = "capability_refs",
    ) -> tuple[dict[str, dict[str, Any]], list[ValidationIssue]]:
        selected: dict[str, dict[str, Any]] = {}
        issues: list[ValidationIssue] = []
        for capability_type, block_id in references.items():
            path = f"{path_prefix}.{capability_type}"
            override_key = (capability_type, block_id)
            prospective = bool(block_overrides and override_key in block_overrides)
            block = (
                block_overrides[override_key]
                if prospective
                else self._blocks.get_block_internal(capability_type, block_id)
            )
            if block is None:
                issues.append(
                    ValidationIssue(
                        code="assembly.reference_not_found",
                        scope=scope,
                        owner_id=owner_id,
                        owner_name=owner_name,
                        path=path,
                        message=(
                            f"The referenced {capability_type} configuration "
                            "does not exist."
                        ),
                        message_key="validation.issue.assembly.referenceNotFound",
                        message_args={"capability_type": capability_type},
                    )
                )
                continue
            selected[capability_type] = block
            issue = self._block_contract_issue(
                capability_type,
                block,
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                stored=not prospective,
            )
            if issue is not None:
                issues.append(issue)
        return selected, issues

    def _resolve_capability_subject(
        self,
        references: dict[str, str],
        *,
        required_types: frozenset[str],
        scope: str,
        owner_id: str,
        owner_name: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> tuple[
        dict[str, dict[str, Any]],
        list[ValidationIssue],
        FilesystemMode,
    ]:
        subject = CapabilityAssemblySubject(
            references=references,
            required_types=required_types,
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
        )
        issues = capability_assembly_issues(subject)
        selected, selected_issues = self._load_references(
            references,
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
            block_overrides=block_overrides,
        )
        issues.extend(selected_issues)
        return selected, issues, subject.filesystem_mode

    def _static_tool_issue(
        self,
        references: dict[str, str],
        blocks: dict[str, dict[str, Any]],
        *,
        has_subagents: bool,
        filesystem_mode: FilesystemMode,
        scope: str,
        owner_id: str,
        owner_name: str,
    ) -> ValidationIssue | None:
        seen: dict[str, str] = (
            {"task": "Deep Agents default harness"} if has_subagents else {}
        )
        if filesystem_mode == "default-shared":
            seen.update(
                {
                    name: "Deep Agents default harness"
                    for name in UNCONFIGURED_FILESYSTEM_TOOL_NAMES
                }
            )
        for capability_type in references:
            manifest = CAPABILITY_BY_TYPE.get(capability_type)
            block = blocks.get(capability_type)
            if manifest is None or block is None:
                continue
            names = list(manifest.tool_names)
            if capability_type == "custom-tool":
                names = []
                resources = block.get("tools", [])
                if not isinstance(resources, list):
                    resources = []
                for resource_name in resources:
                    if not isinstance(resource_name, str):
                        continue
                    try:
                        resource_path = resolve_custom_tool_file(
                            resource_name,
                            self._custom_tools_dir,
                        )
                        if resource_path is None:
                            continue
                        metadata = scan_custom_tool_file(resource_path)
                    except ValueError:
                        # Missing or currently invalid user resources are dynamic
                        # request-preparation failures, not save/start blockers.
                        continue
                    tool_name = metadata.get("tool_name")
                    if isinstance(tool_name, str) and tool_name:
                        names.append(tool_name)
            elif capability_type == "filesystem":
                configs = block.get("tool_configs", {})
                visible_names: list[str] = []
                for name in names:
                    if name == "read_file":
                        visible_names.append(name)
                        continue
                    if name == "execute":
                        continue
                    config = configs.get(name) if isinstance(configs, dict) else None
                    if name == "delete":
                        if isinstance(config, dict) and config.get("visible") is True:
                            visible_names.append(name)
                    elif (
                        not isinstance(config, dict)
                        or config.get("visible") is not False
                    ):
                        visible_names.append(name)
                names = visible_names
            for name in names:
                previous = seen.get(name)
                if previous is not None:
                    return ValidationIssue(
                        code="assembly.tool_name_conflict",
                        scope=scope,
                        owner_id=owner_id,
                        owner_name=owner_name,
                        path=f"tools.{name}",
                        message=(
                            f"Model-visible tool name {name!r} is provided by both "
                            f"{previous} and {capability_type}."
                        ),
                        message_key="validation.issue.assembly.toolNameConflict",
                        message_args={
                            "tool_name": name,
                            "first_capability_type": previous,
                            "second_capability_type": capability_type,
                        },
                    )
                seen[name] = capability_type
        return None

    def _subagent_override(
        self,
        override_id: str,
        *,
        binding: dict[str, Any],
        owner_id: str,
        override_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
        override = (
            override_overrides[override_id]
            if override_overrides and override_id in override_overrides
            else self._agent_configs.get_item("subagent_overrides", override_id)
        )
        if override is None:
            return None, ValidationIssue(
                code="assembly.subagent_override_not_found",
                scope="subagent",
                owner_id=owner_id,
                owner_name=str(binding.get("name", "")),
                path="subagent_override_id",
                message="The referenced Subagent override does not exist.",
                message_key=(
                    "validation.issue.assembly.subagentOverrideNotFound"
                ),
                message_args={},
            )
        try:
            model = SubagentOverrideProfile.model_validate(
                {key: value for key, value in override.items() if key != "id"}
            )
        except ValidationError as exc:
            detail_report = report_from_validation_error(
                exc,
                stage="referenced_subagent_override",
                scope="subagent",
                owner_id=owner_id,
                owner_name=str(binding.get("name", "")),
            )
            detail = (
                detail_report.issues[0].message
                if detail_report.issues
                else "The configuration structure is invalid."
            )
            override_name = str(override.get("name", ""))
            return None, ValidationIssue(
                code="assembly.subagent_override_invalid",
                scope="subagent",
                owner_id=owner_id,
                owner_name=str(binding.get("name", "")),
                path="subagent_override_id",
                message=(
                    f"Referenced Subagent override {override_name!r} does not "
                    f"satisfy the current contract: {detail}"
                ),
                message_key="validation.issue.assembly.subagentOverrideInvalid",
                message_args={
                    "override_name": override_name,
                    "detail": detail,
                },
            )
        return model.model_dump(mode="json"), None

    @staticmethod
    def _prompt_preset_issue(
        block: dict[str, Any] | None,
        *,
        allowed_fields: frozenset[str],
        required_field: str | None,
        scope: str,
        owner_id: str,
        owner_name: str,
        path: str,
    ) -> ValidationIssue | None:
        if block is None:
            if required_field is None:
                return None
            return ValidationIssue(
                code="assembly.prompt_preset_required",
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                message="A Prompt Preset is required for this Agent configuration.",
                message_key="validation.issue.assembly.promptPresetRequired",
                message_args={},
            )
        used: set[str] = set()
        for message in block.get("startup_messages", []):
            template = str(message.get("content_template", ""))
            used.update(
                field_name
                for _literal, field_name, _format, _conversion in Formatter().parse(
                    template
                )
                if field_name is not None
            )
        unsupported = sorted(used - allowed_fields)
        if unsupported:
            return ValidationIssue(
                code="assembly.prompt_preset_scope_invalid",
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                message=(
                    "The selected Prompt Preset uses variables unavailable to this "
                    f"Agent: {', '.join(unsupported)}."
                ),
                message_key="validation.issue.assembly.promptPresetScopeInvalid",
                message_args={"variables": ", ".join(unsupported)},
            )
        if required_field is not None and required_field not in used:
            return ValidationIssue(
                code="assembly.prompt_preset_variable_required",
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                message=(
                    f"The selected Prompt Preset must use {{{required_field}}} in a "
                    "startup message."
                ),
                message_key="validation.issue.assembly.promptPresetVariableRequired",
                message_args={"variable": required_field},
            )
        return None

    def _assemble_primary(
        self,
        primary: dict[str, Any],
        *,
        stage: str,
        owner_id: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        override_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[ValidationReport, StaticAssembly | None]:
        owner_name = str(primary.get("name", ""))
        references = self._reference_map(primary)
        selected, issues, filesystem_mode = self._resolve_capability_subject(
            references,
            required_types=_PRIMARY_REQUIRED_CAPABILITY_TYPES,
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
            block_overrides=block_overrides,
        )
        issues = [
            *subagent_binding_issues(
                list(primary.get("subagents", [])),
                owner_id=owner_id,
                owner_name=owner_name,
            ),
            *issues,
        ]

        delegation_selected = selected.get("subagent") is not None
        bindings = list(primary.get("subagents", [])) if delegation_selected else []
        if delegation_selected and not bindings:
            issues.append(
                ValidationIssue(
                    code="assembly.subagent_binding_required",
                    scope="primary",
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="subagents",
                    message=(
                        "At least one valid Subagent binding is required when "
                        "delegation is enabled."
                    ),
                    message_key=(
                        "validation.issue.assembly.subagentBindingRequired"
                    ),
                    message_args={},
                )
            )

        tool_issue = self._static_tool_issue(
            references,
            selected,
            has_subagents=bool(bindings),
            filesystem_mode=filesystem_mode,
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
        )
        if tool_issue is not None:
            issues.append(tool_issue)

        subagent_nodes: dict[SubagentNodeKey, ResolvedSubagent] = {}
        resolving_nodes: set[SubagentNodeKey] = set()

        def resolve_binding(
            binding: dict[str, Any],
        ) -> ResolvedSubagentEdge | None:
            subagent_name = str(binding.get("name", ""))
            override_id = str(binding.get("subagent_override_id", ""))
            node_key: SubagentNodeKey = (
                override_id,
                subagent_name,
                bool(binding.get("include_client_messages")),
            )
            edge = ResolvedSubagentEdge(binding=binding, target_key=node_key)
            if node_key in subagent_nodes or node_key in resolving_nodes:
                return edge

            resolving_nodes.add(node_key)
            issue_count = len(issues)
            child_references = {
                capability_type: block_id
                for capability_type, block_id in references.items()
                if (
                    CAPABILITY_BY_TYPE.get(capability_type) is None
                    or CAPABILITY_BY_TYPE[capability_type].subagent_policy == "inherit"
                )
            }
            child_bindings: list[dict[str, Any]] = []
            if override_id:
                override, override_issue = self._subagent_override(
                    override_id,
                    binding=binding,
                    owner_id=owner_id,
                    override_overrides=override_overrides,
                )
                if override_issue is not None:
                    issues.append(override_issue)
                    resolving_nodes.remove(node_key)
                    return None
                assert override is not None
                for selection in override["capability_overrides"]:
                    capability_type = selection["type"]
                    if selection["mode"] == "replace":
                        child_references[capability_type] = selection["block_id"]
                    elif selection["mode"] == "disabled":
                        child_references.pop(capability_type, None)
                child_bindings = list(override.get("subagents", []))

            issues.extend(
                subagent_binding_issues(
                    child_bindings,
                    owner_id=owner_id,
                    owner_name=subagent_name,
                )
            )

            (
                child_blocks,
                child_issues,
                child_filesystem_mode,
            ) = self._resolve_capability_subject(
                child_references,
                required_types=_SUBAGENT_REQUIRED_CAPABILITY_TYPES,
                scope="subagent",
                owner_id=owner_id,
                owner_name=subagent_name,
                block_overrides=block_overrides,
            )
            child_tool_issue = self._static_tool_issue(
                child_references,
                child_blocks,
                has_subagents=bool(child_bindings),
                filesystem_mode=child_filesystem_mode,
                scope="subagent",
                owner_id=owner_id,
                owner_name=subagent_name,
            )
            if child_tool_issue is not None:
                child_issues.append(child_tool_issue)
            child_preset_issue = self._prompt_preset_issue(
                child_blocks.get("prompt-preset"),
                allowed_fields=frozenset({"task"}),
                required_field=None,
                scope="subagent",
                owner_id=owner_id,
                owner_name=subagent_name,
                path="capability_refs.prompt-preset",
            )
            if child_preset_issue is not None:
                child_issues.append(child_preset_issue)
            issues.extend(child_issues)
            child_edges: list[ResolvedSubagentEdge] = []
            if len(issues) == issue_count:
                for child_binding in child_bindings:
                    child_edge = resolve_binding(child_binding)
                    if child_edge is not None:
                        child_edges.append(child_edge)

            if len(issues) == issue_count:
                subagent_nodes[node_key] = ResolvedSubagent(
                    key=node_key,
                    name=subagent_name,
                    include_client_messages=bool(
                        binding.get("include_client_messages")
                    ),
                    references=child_references,
                    blocks=child_blocks,
                    filesystem_mode=child_filesystem_mode,
                    subagents=tuple(child_edges),
                )
            resolving_nodes.remove(node_key)
            return edge if node_key in subagent_nodes else None

        resolved_subagents = tuple(
            edge
            for binding in bindings
            if (edge := resolve_binding(binding)) is not None
        )

        primary_preset_issue = self._prompt_preset_issue(
            selected.get("prompt-preset"),
            allowed_fields=frozenset(),
            required_field=None,
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
            path="capability_refs.prompt-preset",
        )
        if primary_preset_issue is not None:
            issues.append(primary_preset_issue)

        report = ValidationReport(stage=stage, issues=tuple(issues))
        if not report.valid:
            return report, None
        return report, StaticAssembly(
            primary=primary,
            references=references,
            blocks=selected,
            filesystem_mode=filesystem_mode,
            subagents=resolved_subagents,
            subagent_nodes=subagent_nodes,
        )

    @staticmethod
    def _issue_key(issue: ValidationIssue) -> tuple[str, str, str, str, str]:
        return (
            issue.code,
            issue.scope,
            issue.owner_id,
            issue.owner_name,
            issue.path,
        )

    def _new_impact_issues(
        self,
        primary: dict[str, Any],
        *,
        stage: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        override_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> list[ValidationIssue]:
        primary_id = str(primary.get("id", ""))
        baseline, _, _ = self.validate_primary(
            primary,
            stage=stage,
            owner_id=primary_id,
            stored=True,
        )
        prospective, _, _ = self.validate_primary(
            primary,
            stage=stage,
            owner_id=primary_id,
            stored=True,
            block_overrides=block_overrides,
            override_overrides=override_overrides,
        )
        baseline_keys = {self._issue_key(issue) for issue in baseline.issues}
        return [
            issue
            for issue in prospective.issues
            if self._issue_key(issue) not in baseline_keys
        ]

    def _impact_issues_for_block(
        self,
        block_type: str,
        block_id: str,
        prospective: dict[str, Any],
        *,
        stage: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for primary in self._agent_configs.list_items("primary_agents"):
            references = primary.get("capability_refs", [])
            if not isinstance(references, list):
                references = []
            direct = any(
                isinstance(item, dict)
                and item.get("type") == block_type
                and item.get("block_id") == block_id
                for item in references
            )
            bindings = primary.get("subagents", [])
            if not isinstance(bindings, list):
                bindings = []
            indirect = self._bindings_reach_block(bindings, block_type, block_id)
            if direct or indirect:
                issues.extend(
                    self._new_impact_issues(
                        primary,
                        stage=stage,
                        block_overrides={(block_type, block_id): prospective},
                    )
                )
        return issues

    def _impact_issues_for_override(
        self,
        override_id: str,
        prospective: dict[str, Any],
        *,
        stage: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for primary in self._agent_configs.list_items("primary_agents"):
            bindings = primary.get("subagents", [])
            if not isinstance(bindings, list):
                continue
            if not self._bindings_reach_override(bindings, override_id):
                continue
            issues.extend(
                self._new_impact_issues(
                    primary,
                    stage=stage,
                    override_overrides={override_id: prospective},
                )
            )
        return issues

    def _bindings_reach_block(
        self,
        bindings: list[Any],
        block_type: str,
        block_id: str,
        *,
        visited: set[str] | None = None,
    ) -> bool:
        visited = set() if visited is None else visited
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            override_id = str(binding.get("subagent_override_id", ""))
            if not override_id or override_id in visited:
                continue
            visited.add(override_id)
            override = self._agent_configs.get_item(
                "subagent_overrides", override_id
            )
            if not override:
                continue
            selections = override.get("capability_overrides", [])
            if isinstance(selections, list) and any(
                isinstance(item, dict)
                and item.get("type") == block_type
                and item.get("mode") == "replace"
                and item.get("block_id") == block_id
                for item in selections
            ):
                return True
            nested = override.get("subagents", [])
            if isinstance(nested, list) and self._bindings_reach_block(
                nested,
                block_type,
                block_id,
                visited=visited,
            ):
                return True
        return False

    def _bindings_reach_override(
        self,
        bindings: list[Any],
        target_id: str,
        *,
        visited: set[str] | None = None,
    ) -> bool:
        visited = set() if visited is None else visited
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            override_id = str(binding.get("subagent_override_id", ""))
            if not override_id:
                continue
            if override_id == target_id:
                return True
            if override_id in visited:
                continue
            visited.add(override_id)
            override = self._agent_configs.get_item(
                "subagent_overrides", override_id
            )
            nested = override.get("subagents", []) if override else []
            if isinstance(nested, list) and self._bindings_reach_override(
                nested,
                target_id,
                visited=visited,
            ):
                return True
        return False
