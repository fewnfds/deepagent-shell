from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    SubagentProfile,
)
from agent_shell.registries.custom_tools import (
    resolve_custom_tool_file,
    scan_custom_tool_file,
)
from agent_shell.storage.agent_configs import AgentConfigStore
from agent_shell.storage.automation import AutomationStore
from agent_shell.storage.blocks import BlockStore
from agent_shell.automation.validation import AutomationValidationService
from agent_shell.validation.capability_assembly import (
    CapabilityAssemblySubject,
    FilesystemMode,
    capability_assembly_issues,
)
from agent_shell.validation.contracts import report_from_validation_error
from agent_shell.validation.models import ValidationIssue, ValidationReport
from agent_shell.validation.subagent_references import subagent_reference_issues


SubagentNodeKey = str


@dataclass(frozen=True, slots=True)
class ResolvedSubagentEdge:
    target_key: SubagentNodeKey


@dataclass(frozen=True, slots=True)
class ResolvedSubagent:
    key: SubagentNodeKey
    component_name: str
    name: str
    description: str
    references: dict[str, str]
    blocks: dict[str, dict[str, Any]]
    filesystem_mode: FilesystemMode
    hook_workflow: dict[str, Any] | None
    lifecycle_workflow: dict[str, Any] | None
    subagents: tuple[ResolvedSubagentEdge, ...]


@dataclass(frozen=True, slots=True)
class StaticAssembly:
    primary: dict[str, Any]
    references: dict[str, str]
    blocks: dict[str, dict[str, Any]]
    filesystem_mode: FilesystemMode
    hook_workflow: dict[str, Any] | None
    lifecycle_workflow: dict[str, Any] | None
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
        automation: AutomationStore,
        automation_validation: AutomationValidationService,
        *,
        custom_tools_dir: Path,
    ) -> None:
        self._blocks = blocks
        self._agent_configs = agent_configs
        self._automation = automation
        self._automation_validation = automation_validation
        self._custom_tools_dir = custom_tools_dir

    def validate_primary(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
        stored: bool = False,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
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
            profile_overrides=profile_overrides,
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

    def validate_subagent(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        owner_id: str = "",
        stored: bool = False,
    ) -> tuple[ValidationReport, dict[str, Any] | None]:
        try:
            model = SubagentProfile.model_validate(
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
                    scope="subagent",
                    owner_id=owner_id,
                    owner_name=str(payload.get("component_name", "")),
                ),
                None,
            )
        validated = model.model_dump(mode="json")
        settings = validated["settings"]
        references = {
            item["type"]: item["block_id"]
            for item in settings["capability_overrides"]
            if item["mode"] == "replace"
        }
        _, issues = self._load_references(
            references,
            scope="subagent",
            owner_id=owner_id,
            owner_name=validated["component_name"],
            path_prefix="settings.capability_overrides",
        )
        automation = settings.get("automation", {})
        for workflow_type, selection_name in (
            ("hook-workflow", "hook_workflow"),
            ("lifecycle-workflow", "lifecycle_workflow"),
        ):
            selection = automation.get(selection_name, {})
            if selection.get("mode") != "replace":
                continue
            _workflow, workflow_issue = self._workflow_reference(
                workflow_type,
                str(selection.get("workflow_id", "")),
                scope="subagent",
                owner_id=owner_id,
                owner_name=validated["component_name"],
                path=f"settings.automation.{selection_name}.workflow_id",
            )
            if workflow_issue is not None:
                issues.append(workflow_issue)
        child_references = list(settings.get("subagents", []))
        child_profiles: dict[str, dict[str, Any]] = {}
        for index, reference in enumerate(child_references):
            target_id = str(reference.get("subagent_id", ""))
            if target_id == owner_id:
                child_profiles[target_id] = validated
                continue
            target, target_issue = self._subagent_profile(
                target_id,
                owner_id=owner_id,
                owner_name=validated["component_name"],
                path=f"settings.subagents[{index}].subagent_id",
            )
            if target_issue is not None:
                issues.append(target_issue)
            elif target is not None:
                child_profiles[target_id] = target
        issues.extend(
            subagent_reference_issues(
                child_references,
                profiles=child_profiles,
                scope="subagent",
                owner_id=owner_id,
                owner_name=validated["component_name"],
                path_prefix="settings.subagents",
            )
        )
        if owner_id and not issues:
            prospective = dict(validated)
            prospective["id"] = owner_id
            issues.extend(
                self._impact_issues_for_subagent(
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
        for workflow_type in ("hook-workflow", "lifecycle-workflow"):
            for workflow in self._automation.list_items(workflow_type):
                report, _ = self._automation_validation.validate_workflow(
                    workflow_type,
                    workflow,
                    stage=stage,
                    owner_id=str(workflow.get("id", "")),
                    stored=True,
                )
                issues.extend(report.issues)
        for profile in self._agent_configs.list_items("subagents"):
            report, _ = self.validate_subagent(
                profile,
                stage=stage,
                owner_id=str(profile.get("id", "")),
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

    def _subagent_profile(
        self,
        profile_id: str,
        *,
        owner_id: str,
        owner_name: str,
        path: str,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
        profile = (
            profile_overrides[profile_id]
            if profile_overrides and profile_id in profile_overrides
            else self._agent_configs.get_item("subagents", profile_id)
        )
        if profile is None:
            return None, ValidationIssue(
                code="assembly.subagent_not_found",
                scope="subagent",
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                message="The referenced Subagent entity does not exist.",
                message_key="validation.issue.assembly.subagentNotFound",
                message_args={},
            )
        try:
            model = SubagentProfile.model_validate(
                {key: value for key, value in profile.items() if key != "id"}
            )
        except ValidationError as exc:
            detail_report = report_from_validation_error(
                exc,
                stage="referenced_subagent",
                scope="subagent",
                owner_id=owner_id,
                owner_name=owner_name,
            )
            detail = (
                detail_report.issues[0].message
                if detail_report.issues
                else "The configuration structure is invalid."
            )
            component_name = str(profile.get("component_name", ""))
            return None, ValidationIssue(
                code="assembly.subagent_invalid",
                scope="subagent",
                owner_id=owner_id,
                owner_name=owner_name,
                path=path,
                message=(
                    f"Referenced Subagent {component_name!r} does not "
                    f"satisfy the current contract: {detail}"
                ),
                message_key="validation.issue.assembly.subagentInvalid",
                message_args={
                    "component_name": component_name,
                    "detail": detail,
                },
            )
        return model.model_dump(mode="json"), None

    def _workflow_reference(
        self,
        workflow_type: str,
        workflow_id: str,
        *,
        scope: str,
        owner_id: str,
        owner_name: str,
        path: str,
    ) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
        if not workflow_id:
            return None, None
        workflow = self._automation.get_item(workflow_type, workflow_id)
        if workflow is not None:
            report, validated = self._automation_validation.validate_workflow(
                workflow_type,
                workflow,
                stage="request_prepare",
                owner_id=workflow_id,
                stored=True,
            )
            if report.valid:
                assert validated is not None
                return {"id": workflow_id, **validated}, None
            return None, report.issues[0]
        return None, ValidationIssue(
            code="assembly.workflow_not_found",
            scope=scope,
            owner_id=owner_id,
            owner_name=owner_name,
            path=path,
            message="The referenced automation workflow does not exist.",
            message_key="validation.issue.assembly.workflowNotFound",
            message_args={"workflow_type": workflow_type},
        )

    def _assemble_primary(
        self,
        primary: dict[str, Any],
        *,
        stage: str,
        owner_id: str,
        block_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
        profile_overrides: dict[str, dict[str, Any]] | None = None,
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
        primary_automation = primary.get("automation", {})
        primary_hook, hook_issue = self._workflow_reference(
            "hook-workflow",
            str(primary_automation.get("hook_workflow_id", "")),
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
            path="automation.hook_workflow_id",
        )
        primary_lifecycle, lifecycle_issue = self._workflow_reference(
            "lifecycle-workflow",
            str(primary_automation.get("lifecycle_workflow_id", "")),
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
            path="automation.lifecycle_workflow_id",
        )
        issues.extend(issue for issue in (hook_issue, lifecycle_issue) if issue)

        delegation_selected = selected.get("subagent") is not None
        root_references = list(primary.get("subagents", []))
        active_roots = root_references if delegation_selected else []
        if delegation_selected and not active_roots:
            issues.append(
                ValidationIssue(
                    code="assembly.subagent_reference_required",
                    scope="primary",
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path="subagents",
                    message=(
                        "At least one valid Subagent reference is required when "
                        "delegation is enabled."
                    ),
                    message_key=(
                        "validation.issue.assembly.subagentReferenceRequired"
                    ),
                    message_args={},
                )
            )

        tool_issue = self._static_tool_issue(
            references,
            selected,
            has_subagents=bool(active_roots),
            filesystem_mode=filesystem_mode,
            scope="primary",
            owner_id=owner_id,
            owner_name=owner_name,
        )
        if tool_issue is not None:
            issues.append(tool_issue)

        subagent_nodes: dict[SubagentNodeKey, ResolvedSubagent] = {}
        resolving_nodes: set[SubagentNodeKey] = set()
        known_profiles: dict[str, dict[str, Any]] = {}

        def resolve_reference(
            reference: dict[str, Any],
            *,
            parent_id: str,
            parent_name: str,
            path: str,
        ) -> ResolvedSubagentEdge | None:
            profile_id = str(reference.get("subagent_id", ""))
            edge = ResolvedSubagentEdge(target_key=profile_id)
            if profile_id in subagent_nodes or profile_id in resolving_nodes:
                return edge

            profile, profile_issue = self._subagent_profile(
                profile_id,
                owner_id=parent_id,
                owner_name=parent_name,
                path=path,
                profile_overrides=profile_overrides,
            )
            if profile_issue is not None:
                issues.append(profile_issue)
                return None
            assert profile is not None
            known_profiles[profile_id] = profile

            resolving_nodes.add(profile_id)
            issue_count = len(issues)
            child_references = {
                capability_type: block_id
                for capability_type, block_id in references.items()
                if (
                    CAPABILITY_BY_TYPE.get(capability_type) is None
                    or CAPABILITY_BY_TYPE[capability_type].subagent_policy == "inherit"
                )
            }
            settings = profile["settings"]
            for selection in settings["capability_overrides"]:
                capability_type = selection["type"]
                if selection["mode"] == "replace":
                    child_references[capability_type] = selection["block_id"]
                elif selection["mode"] == "disabled":
                    child_references.pop(capability_type, None)
            child_profile_references = (
                list(settings.get("subagents", []))
                if "subagent" in child_references
                else []
            )
            subagent_name = str(profile["name"])

            child_automation = settings.get("automation", {})

            def resolve_child_workflow(
                workflow_type: str,
                selection_name: str,
                inherited: dict[str, Any] | None,
            ) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
                selection = child_automation.get(selection_name, {})
                mode = selection.get("mode", "inherit")
                if mode == "inherit":
                    return inherited, None
                if mode == "disabled":
                    return None, None
                return self._workflow_reference(
                    workflow_type,
                    str(selection.get("workflow_id", "")),
                    scope="subagent",
                    owner_id=profile_id,
                    owner_name=subagent_name,
                    path=f"settings.automation.{selection_name}.workflow_id",
                )

            child_hook, child_hook_issue = resolve_child_workflow(
                "hook-workflow", "hook_workflow", primary_hook
            )
            child_lifecycle, child_lifecycle_issue = resolve_child_workflow(
                "lifecycle-workflow", "lifecycle_workflow", primary_lifecycle
            )

            (
                child_blocks,
                child_issues,
                child_filesystem_mode,
            ) = self._resolve_capability_subject(
                child_references,
                required_types=_SUBAGENT_REQUIRED_CAPABILITY_TYPES,
                scope="subagent",
                owner_id=profile_id,
                owner_name=subagent_name,
                block_overrides=block_overrides,
            )
            child_tool_issue = self._static_tool_issue(
                child_references,
                child_blocks,
                has_subagents=bool(child_profile_references),
                filesystem_mode=child_filesystem_mode,
                scope="subagent",
                owner_id=profile_id,
                owner_name=subagent_name,
            )
            if child_tool_issue is not None:
                child_issues.append(child_tool_issue)
            child_issues.extend(
                issue
                for issue in (child_hook_issue, child_lifecycle_issue)
                if issue is not None
            )
            issues.extend(child_issues)
            child_edges: list[ResolvedSubagentEdge] = []
            if len(issues) == issue_count:
                for index, child_reference in enumerate(child_profile_references):
                    child_edge = resolve_reference(
                        child_reference,
                        parent_id=profile_id,
                        parent_name=str(profile["component_name"]),
                        path=f"settings.subagents[{index}].subagent_id",
                    )
                    if child_edge is not None:
                        child_edges.append(child_edge)
                issues.extend(
                    subagent_reference_issues(
                        child_profile_references,
                        profiles=known_profiles,
                        scope="subagent",
                        owner_id=profile_id,
                        owner_name=str(profile["component_name"]),
                        path_prefix="settings.subagents",
                    )
                )

            if len(issues) == issue_count:
                subagent_nodes[profile_id] = ResolvedSubagent(
                    key=profile_id,
                    component_name=str(profile["component_name"]),
                    name=subagent_name,
                    description=str(profile["description"]),
                    references=child_references,
                    blocks=child_blocks,
                    filesystem_mode=child_filesystem_mode,
                    hook_workflow=child_hook,
                    lifecycle_workflow=child_lifecycle,
                    subagents=tuple(child_edges),
                )
            resolving_nodes.remove(profile_id)
            return edge if profile_id in subagent_nodes else None

        resolved_subagents = tuple(
            edge
            for index, reference in enumerate(active_roots)
            if (
                edge := resolve_reference(
                    reference,
                    parent_id=owner_id,
                    parent_name=owner_name,
                    path=f"subagents[{index}].subagent_id",
                )
            )
            is not None
        )
        if not delegation_selected:
            for index, reference in enumerate(root_references):
                profile_id = str(reference.get("subagent_id", ""))
                profile, profile_issue = self._subagent_profile(
                    profile_id,
                    owner_id=owner_id,
                    owner_name=owner_name,
                    path=f"subagents[{index}].subagent_id",
                    profile_overrides=profile_overrides,
                )
                if profile_issue is not None:
                    issues.append(profile_issue)
                elif profile is not None:
                    known_profiles[profile_id] = profile
        issues.extend(
            subagent_reference_issues(
                root_references,
                profiles=known_profiles,
                scope="primary",
                owner_id=owner_id,
                owner_name=owner_name,
            )
        )

        report = ValidationReport(stage=stage, issues=tuple(issues))
        if not report.valid:
            return report, None
        return report, StaticAssembly(
            primary=primary,
            references=references,
            blocks=selected,
            filesystem_mode=filesystem_mode,
            hook_workflow=primary_hook,
            lifecycle_workflow=primary_lifecycle,
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
        profile_overrides: dict[str, dict[str, Any]] | None = None,
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
            profile_overrides=profile_overrides,
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
            subagent_references = primary.get("subagents", [])
            if not isinstance(subagent_references, list):
                subagent_references = []
            indirect = self._subagents_reach_block(
                subagent_references, block_type, block_id
            )
            if direct or indirect:
                issues.extend(
                    self._new_impact_issues(
                        primary,
                        stage=stage,
                        block_overrides={(block_type, block_id): prospective},
                    )
                )
        return issues

    def _impact_issues_for_subagent(
        self,
        profile_id: str,
        prospective: dict[str, Any],
        *,
        stage: str,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for primary in self._agent_configs.list_items("primary_agents"):
            subagent_references = primary.get("subagents", [])
            if not isinstance(subagent_references, list):
                continue
            if not self._references_reach_subagent(
                subagent_references, profile_id
            ):
                continue
            issues.extend(
                self._new_impact_issues(
                    primary,
                    stage=stage,
                    profile_overrides={profile_id: prospective},
                )
            )
        return issues

    def _subagents_reach_block(
        self,
        references: list[Any],
        block_type: str,
        block_id: str,
        *,
        visited: set[str] | None = None,
    ) -> bool:
        visited = set() if visited is None else visited
        for reference in references:
            if not isinstance(reference, dict):
                continue
            profile_id = str(reference.get("subagent_id", ""))
            if not profile_id or profile_id in visited:
                continue
            visited.add(profile_id)
            profile = self._agent_configs.get_item("subagents", profile_id)
            if not profile:
                continue
            settings = profile.get("settings", {})
            if not isinstance(settings, dict):
                continue
            selections = settings.get("capability_overrides", [])
            if isinstance(selections, list) and any(
                isinstance(item, dict)
                and item.get("type") == block_type
                and item.get("mode") == "replace"
                and item.get("block_id") == block_id
                for item in selections
            ):
                return True
            nested = settings.get("subagents", [])
            if isinstance(nested, list) and self._subagents_reach_block(
                nested,
                block_type,
                block_id,
                visited=visited,
            ):
                return True
        return False

    def _references_reach_subagent(
        self,
        references: list[Any],
        target_id: str,
        *,
        visited: set[str] | None = None,
    ) -> bool:
        visited = set() if visited is None else visited
        for reference in references:
            if not isinstance(reference, dict):
                continue
            profile_id = str(reference.get("subagent_id", ""))
            if not profile_id:
                continue
            if profile_id == target_id:
                return True
            if profile_id in visited:
                continue
            visited.add(profile_id)
            profile = self._agent_configs.get_item("subagents", profile_id)
            settings = profile.get("settings", {}) if profile else {}
            nested = settings.get("subagents", []) if isinstance(settings, dict) else []
            if isinstance(nested, list) and self._references_reach_subagent(
                nested,
                target_id,
                visited=visited,
            ):
                return True
        return False
