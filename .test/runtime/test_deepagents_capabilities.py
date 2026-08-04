from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest
from pydantic import ValidationError

from agent_shell.contracts import (
    FilesystemBlock,
    FilesystemPermissionsBlock,
    SkillBlock,
)
from agent_shell.runtime.capabilities import (
    DeepAgentsCapabilityError,
    build_deepagents_capabilities,
)
from agent_shell.runtime.capabilities import deepagents as deepagents_capability


def test_skill_requires_at_least_one_selection() -> None:
    with pytest.raises(ValidationError, match="At least one Skill"):
        SkillBlock.model_validate({"name": "Empty skills", "skills": []})

    unicode_name = SkillBlock.model_validate(
        {"name": "Unicode skill", "skills": ["café"]}
    )
    assert unicode_name.skills == ["café"]
    with pytest.raises(ValidationError, match="single hyphens"):
        SkillBlock.model_validate(
            {"name": "Invalid skill name", "skills": ["bad--name"]}
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SkillBlock.model_validate(
            {"name": "Removed switch", "enabled": False, "skills": ["valid"]}
        )


def test_selected_skill_with_invalid_current_metadata_is_not_materialized(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "invalid-metadata"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: invalid-metadata\n---\n",
        encoding="utf-8",
    )
    filesystem = FilesystemBlock.model_validate({"name": "Thread files"})
    skill = SkillBlock.model_validate(
        {"name": "Invalid metadata", "skills": ["invalid-metadata"]}
    )

    with pytest.raises(DeepAgentsCapabilityError, match="selected skill is invalid"):
        build_deepagents_capabilities(
            filesystem,
            skill,
            filesystem_mode="configured-shared",
            skills_dir=skills_dir,
        )


def test_filesystem_runtime_options_and_tool_switches_are_compiled(tmp_path: Path) -> None:
    mapped = tmp_path / "mapped"
    mapped.mkdir()
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    filesystem = FilesystemBlock.model_validate(
        {
            "name": "Workspace",
            "mapped_directories": [
                {"virtual_path": "/workspace/", "local_path": str(mapped)}
            ],
            "system_prompt_override": "Use the configured workspace only.",
            "tool_token_limit_before_evict": 4096,
            "tool_configs": {
                "ls": {"visible": False},
                "read_file": {
                    "visible": True,
                    "description_override": "Read a configured workspace file.",
                },
                "delete": {
                    "visible": True,
                    "description_override": "Delete a configured workspace path.",
                },
            },
        }
    )

    capabilities = build_deepagents_capabilities(
        filesystem,
        None,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )
    middleware = capabilities.middleware[0]

    assert middleware.backend is capabilities.backend
    assert [tool.name for tool in middleware.tools] == [
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
    ]
    assert middleware._enabled_tools == frozenset(
        {"read_file", "write_file", "edit_file", "delete", "glob", "grep"}
    )
    assert middleware._custom_system_prompt == "Use the configured workspace only."
    assert middleware._custom_tool_descriptions == {
        "read_file": "Read a configured workspace file.",
        "delete": "Delete a configured workspace path.",
    }
    assert middleware._tool_token_limit_before_evict == 4096


def test_filesystem_permissions_atomically_override_tools_prompt_and_paths(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    filesystem = FilesystemBlock.model_validate(
        {
            "name": "Workspace",
            "system_prompt_override": "Base filesystem prompt",
            "tool_configs": {
                "ls": {
                    "visible": True,
                    "description_override": "Base list description",
                },
                "write_file": {"visible": True},
            },
        }
    )
    permissions = FilesystemPermissionsBlock.model_validate(
        {
            "name": "Reviewer",
            "permissions": [
                {"path": "/source/**", "permission": "read-only"},
                {"path": "/output/**", "permission": "read-write"},
                {"path": "/private/**", "permission": "no-access"},
                {"path": "/skills/**", "permission": "no-access"},
            ],
            "system_prompt_override": {"value": "Policy prompt"},
            "tool_overrides": {
                "ls": {"visible": False, "description_override": None},
                "write_file": {
                    "visible": True,
                    "description_override": "Policy write description",
                },
            },
        }
    )

    capabilities = build_deepagents_capabilities(
        filesystem,
        None,
        filesystem_permissions=permissions,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )
    middleware = capabilities.middleware[0]

    assert "ls" not in {tool.name for tool in middleware.tools}
    assert middleware._custom_system_prompt == "Policy prompt"
    assert middleware._custom_tool_descriptions == {
        "write_file": "Policy write description"
    }
    rules = [
        (tuple(rule.operations), tuple(rule.paths), rule.mode)
        for rule in capabilities.permissions
    ]
    assert rules == [
        (("read",), ("/skills/**",), "allow"),
        (("write",), ("/skills/**",), "deny"),
        (("read",), ("/source/**",), "allow"),
        (("write",), ("/source/**",), "deny"),
        (("read", "write"), ("/output/**",), "allow"),
        (("read", "write"), ("/private/**",), "deny"),
        (("read", "write"), ("/skills/**",), "deny"),
    ]
    assert middleware._permissions == list(capabilities.permissions)
    from deepagents.middleware.filesystem import _check_fs_permission

    assert (
        _check_fs_permission(
            list(capabilities.permissions), "read", "/skills/demo/SKILL.md"
        )
        == "allow"
    )
    assert (
        _check_fs_permission(
            list(capabilities.permissions), "write", "/skills/demo/SKILL.md"
        )
        == "deny"
    )


def test_request_seed_file_data_uses_string_content_for_text_and_binary(
    tmp_path: Path,
) -> None:
    text_source = tmp_path / "note.txt"
    text_source.write_text("request text", encoding="utf-8")
    binary_source = tmp_path / "payload.bin"
    binary_source.write_bytes(b"\xff\x00")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    filesystem = FilesystemBlock.model_validate(
        {
            "name": "Seed files",
            "virtual_files": [
                {"virtual_path": "/input/note.txt", "source_path": str(text_source)},
                {
                    "virtual_path": "/input/payload.bin",
                    "source_path": str(binary_source),
                },
            ],
        }
    )

    capabilities = build_deepagents_capabilities(
        filesystem,
        None,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )

    text_data = capabilities.initial_files["/input/note.txt"]
    binary_data = capabilities.initial_files["/input/payload.bin"]
    assert isinstance(text_data["content"], str)
    assert text_data["content"] == "request text"
    assert text_data["encoding"] == "utf-8"
    assert isinstance(binary_data["content"], str)
    assert binary_data["content"] == "/wA="
    assert binary_data["encoding"] == "base64"


def test_virtual_directory_rejects_links_before_reading_outside_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside sentinel", encoding="utf-8")
    link = source / "leak.txt"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symbolic links are unavailable in this environment: {exc}")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    filesystem = FilesystemBlock.model_validate(
        {
            "name": "Linked source",
            "virtual_directories": [
                {"virtual_path": "/source/", "source_path": str(source)}
            ],
        }
    )

    with pytest.raises(
        DeepAgentsCapabilityError,
        match="links and reparse points are not supported",
    ):
        build_deepagents_capabilities(
            filesystem,
            None,
            filesystem_mode="configured-shared",
            skills_dir=skills_dir,
        )


def test_virtual_source_rejects_windows_reparse_points(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class ReparsePointStat:
        st_mode = stat.S_IFREG
        st_file_attributes = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

    monkeypatch.setattr(
        deepagents_capability,
        "_source_stat",
        lambda path: ReparsePointStat(),
    )

    with pytest.raises(
        DeepAgentsCapabilityError,
        match="links and reparse points are not supported",
    ):
        deepagents_capability._assert_plain_source(tmp_path / "reparse-source")


def test_filesystem_runtime_options_keep_upstream_defaults_or_disable_eviction(
    tmp_path: Path,
) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    filesystem = FilesystemBlock.model_validate(
        {
            "name": "Thread files",
            "tool_token_limit_before_evict": None,
        }
    )

    capabilities = build_deepagents_capabilities(
        filesystem,
        None,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )
    middleware = capabilities.middleware[0]

    assert middleware._custom_system_prompt is None
    assert middleware._tool_token_limit_before_evict is None
    assert "delete" not in {tool.name for tool in middleware.tools}


def test_skill_prompt_supports_default_override_and_disabled_modes(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "outline"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: outline\ndescription: Outline a document.\n---\n",
        encoding="utf-8",
    )
    filesystem = FilesystemBlock.model_validate({"name": "Thread files"})
    default_skill = SkillBlock.model_validate(
        {"name": "Default skills", "skills": ["outline"]}
    )
    custom_prompt = (
        "Locations: {skills_locations}\n"
        "Warnings: {skills_load_warnings}\n"
        "Skills: {skills_list}"
    )
    custom_skill = SkillBlock.model_validate(
        {
            "name": "Custom skills",
            "skills": ["outline"],
            "instruction_override": custom_prompt,
        }
    )
    disabled_skill = SkillBlock.model_validate(
        {
            "name": "Silent skills",
            "skills": ["outline"],
            "system_prompt_enabled": False,
        }
    )
    with pytest.raises(ValidationError, match="instruction_override must be null"):
        SkillBlock.model_validate(
            {
                "name": "Ambiguous skills",
                "skills": ["outline"],
                "system_prompt_enabled": False,
                "instruction_override": custom_prompt,
            }
        )

    default_capabilities = build_deepagents_capabilities(
        filesystem,
        default_skill,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )
    custom_capabilities = build_deepagents_capabilities(
        filesystem,
        custom_skill,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )
    disabled_capabilities = build_deepagents_capabilities(
        filesystem,
        disabled_skill,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )

    assert default_capabilities.middleware[0].system_prompt_template != custom_prompt
    assert custom_capabilities.middleware[0].system_prompt_template == custom_prompt
    assert disabled_capabilities.middleware[0].system_prompt_template is None


def test_default_workspace_keeps_consumer_skill_overlays_read_only_and_isolated(
    tmp_path: Path,
) -> None:
    from deepagents.backends import StateBackend

    skills_dir = tmp_path / "skills"
    for name in ("alpha", "beta"):
        folder = skills_dir / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} instructions.\n---\n",
            encoding="utf-8",
        )
    alpha = SkillBlock.model_validate(
        {"name": "Alpha only", "skills": ["alpha"]}
    )
    beta = SkillBlock.model_validate(
        {"name": "Beta only", "skills": ["beta"]}
    )

    alpha_capabilities = build_deepagents_capabilities(
        None,
        alpha,
        filesystem_mode="default-shared",
        skills_dir=skills_dir,
    )
    beta_capabilities = build_deepagents_capabilities(
        None,
        beta,
        filesystem_mode="default-shared",
        skills_dir=skills_dir,
        workspace=alpha_capabilities.workspace,
    )

    alpha_filesystem = alpha_capabilities.middleware[-1]
    assert [tool.name for tool in alpha_filesystem.tools] == [
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
    ]
    assert alpha_filesystem._tool_token_limit_before_evict is None
    assert isinstance(alpha_capabilities.backend.default, StateBackend)
    assert alpha_capabilities.backend is not beta_capabilities.backend
    assert alpha_capabilities.workspace is beta_capabilities.workspace
    assert alpha_capabilities.backend.default is beta_capabilities.backend.default
    assert alpha_capabilities.skill_sources == ("/skills/alpha/",)
    assert beta_capabilities.skill_sources == ("/skills/beta/",)
    assert alpha_capabilities.backend.read(
        "/skills/alpha/SKILL.md"
    ).error is None
    assert "not found" in alpha_capabilities.backend.read(
        "/skills/beta/SKILL.md"
    ).error.lower()
    assert beta_capabilities.backend.read(
        "/skills/beta/SKILL.md"
    ).error is None
    assert "not found" in beta_capabilities.backend.read(
        "/skills/alpha/SKILL.md"
    ).error.lower()
    denied = alpha_capabilities.backend.write(
        "/skills/alpha/created.md", "must not be written"
    )
    assert "read-only" in denied.error
    assert not (skills_dir / "alpha" / "created.md").exists()


def test_configured_workspace_routes_entire_skill_namespace_away_from_state(
    tmp_path: Path,
) -> None:
    from deepagents.backends import StateBackend

    skills_dir = tmp_path / "skills"
    selected_folder = skills_dir / "selected"
    selected_folder.mkdir(parents=True)
    manifest = selected_folder / "SKILL.md"
    manifest.write_text(
        "---\nname: selected\ndescription: Selected instructions.\n---\n",
        encoding="utf-8",
    )
    filesystem = FilesystemBlock.model_validate({"name": "Shared workspace"})
    skill = SkillBlock.model_validate(
        {"name": "Selected Skill", "skills": ["selected"]}
    )

    capabilities = build_deepagents_capabilities(
        filesystem,
        skill,
        filesystem_mode="configured-shared",
        skills_dir=skills_dir,
    )

    assert isinstance(capabilities.backend.default, StateBackend)
    skills_backend = capabilities.backend.routes["/skills/"]
    routed_backend, routed_path = capabilities.backend._get_backend_and_key(
        "/skills/unselected/SKILL.md"
    )
    assert routed_backend is skills_backend
    assert routed_path == "/unselected/SKILL.md"
    assert "not found" in capabilities.backend.read(
        "/skills/unselected/SKILL.md"
    ).error.lower()
    denied = capabilities.backend.edit(
        "/skills/selected/SKILL.md",
        "Selected instructions.",
        "Changed instructions.",
    )
    assert "read-only" in denied.error
    assert "Selected instructions." in manifest.read_text(encoding="utf-8")
