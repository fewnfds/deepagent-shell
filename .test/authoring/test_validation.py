from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_shell.contracts import SystemPromptBlock
from agent_shell.validation import ValidationIssue, report_from_validation_error


def test_contract_errors_become_safe_structured_validation_issues() -> None:
    try:
        SystemPromptBlock.model_validate(
            {
                "name": "",
                "system_prompt": "",
                "legacy_field": r"C:\private\legacy.json",
            }
        )
    except ValidationError as exc:
        report = report_from_validation_error(
            exc,
            stage="block_save",
            scope="block",
            owner_id="block-id",
            owner_name="旧配置",
        )
    else:  # pragma: no cover - the strict contract must reject this payload
        raise AssertionError("invalid payload unexpectedly passed")

    payload = report.as_dict()
    assert payload["valid"] is False
    assert payload["stage"] == "block_save"
    assert {issue["path"] for issue in payload["issues"]} == {
        "name",
        "system_prompt",
        "legacy_field",
    }
    assert any(
        issue["code"] == "contract.unknown_field"
        for issue in payload["issues"]
    )
    assert all(issue["scope"] == "block" for issue in payload["issues"])
    assert {issue["message_key"] for issue in payload["issues"]} == {
        "validation.issue.contract.textTooShort",
        "validation.issue.contract.unknownField",
    }
    assert all(issue["message_args"] == {} for issue in payload["issues"])
    assert all("private" not in issue["message"] for issue in payload["issues"])
    assert all("legacy.json" not in issue["message"] for issue in payload["issues"])


def test_validation_issue_redacts_user_controlled_owner_path_and_message() -> None:
    issue = ValidationIssue(
        code="contract.invalid_value",
        scope="block",
        owner_id=r"C:\private\owner-id",
        owner_name="sk-1234567890-private",
        path=r"legacy.C:\private\field.json",
        message=r"Invalid C:\private\payload.json with Bearer top-secret-token",
        message_key="validation.issue.contract.invalidValue",
        message_args={
            "detail": r"Invalid C:\private\payload.json with Bearer top-secret-token"
        },
    ).as_dict()

    serialized = str(issue)
    assert "C:\\private" not in serialized
    assert "sk-1234567890-private" not in serialized
    assert "top-secret-token" not in serialized
    assert "[LOCAL_PATH]" in serialized
    assert "[REDACTED]" in serialized
    assert issue["message_key"] == "validation.issue.contract.invalidValue"


def test_validation_issue_rejects_non_primitive_message_arguments() -> None:
    with pytest.raises(TypeError, match="finite JSON primitive"):
        ValidationIssue(
            code="contract.invalid_value",
            scope="block",
            path="name",
            message="Invalid value.",
            message_key="validation.issue.contract.invalidValue",
            message_args={"detail": {"nested": "value"}},  # type: ignore[dict-item]
        )
