from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import ValidationError

from agent_shell.localization import MessageArg
from agent_shell.redaction import redact_for_boundary
from agent_shell.validation.models import ValidationIssue, ValidationReport


_ERROR_CODES = {
    "extra_forbidden": "contract.unknown_field",
    "missing": "contract.field_required",
    "string_too_short": "contract.text_too_short",
    "string_too_long": "contract.text_too_long",
    "too_short": "contract.collection_too_short",
    "too_long": "contract.collection_too_long",
    "literal_error": "contract.invalid_choice",
    "enum": "contract.invalid_choice",
    "finite_number": "contract.number_not_finite",
    "output_event_types_invalid": "contract.output_event_types_invalid",
    "output_template_empty": "contract.output_template_empty",
    "output_template_malformed": "contract.output_template_malformed",
    "output_template_unknown_variables": "contract.output_template_unknown_variables",
}

_ERROR_MESSAGE_KEYS = {
    "extra_forbidden": "validation.issue.contract.unknownField",
    "missing": "validation.issue.contract.fieldRequired",
    "string_too_short": "validation.issue.contract.textTooShort",
    "string_too_long": "validation.issue.contract.textTooLong",
    "too_short": "validation.issue.contract.collectionTooShort",
    "too_long": "validation.issue.contract.collectionTooLong",
    "literal_error": "validation.issue.contract.invalidChoice",
    "enum": "validation.issue.contract.invalidChoice",
    "finite_number": "validation.issue.contract.numberNotFinite",
    "output_event_types_invalid": "validation.issue.contract.outputEventTypesInvalid",
    "output_template_empty": "validation.issue.contract.outputTemplateEmpty",
    "output_template_malformed": "validation.issue.contract.outputTemplateMalformed",
    "output_template_unknown_variables": "validation.issue.contract.outputTemplateUnknownVariables",
}

_ERROR_ARG_KEYS = {
    "output_event_types_invalid": ("details",),
    "output_template_empty": ("event_name",),
    "output_template_malformed": ("event_name",),
    "output_template_unknown_variables": ("event_name", "variables"),
}

_ERROR_MESSAGES = {
    "extra_forbidden": "The field is not accepted by the current contract.",
    "missing": "A required field is missing.",
    "string_too_short": "The text is shorter than the allowed range.",
    "string_too_long": "The text is longer than the allowed range.",
    "too_short": "The collection contains too few items.",
    "too_long": "The collection contains too many items.",
    "literal_error": "The value is not one of the allowed choices.",
    "enum": "The value is not one of the allowed choices.",
    "finite_number": "The value must be a finite number.",
}


def _path(loc: Iterable[object]) -> str:
    result = ""
    for part in loc:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += ("." if result else "") + str(part)
    return result


def _safe_message(error: dict[str, object]) -> str:
    error_type = str(error.get("type", ""))
    known = _ERROR_MESSAGES.get(error_type)
    if known:
        return known
    raw = str(error.get("msg") or "The value does not satisfy the contract.")
    if raw.startswith("Value error, "):
        raw = raw[len("Value error, ") :]
    safe = redact_for_boundary("preflight-diagnostic", raw)
    return (
        safe
        if isinstance(safe, str) and safe
        else "The value does not satisfy the contract."
    )


def _message_args(
    error_type: str, error: dict[str, object]
) -> dict[str, MessageArg]:
    context = error.get("ctx")
    if not isinstance(context, dict):
        return {}
    result: dict[str, MessageArg] = {}
    for key in _ERROR_ARG_KEYS.get(error_type, ()):
        value = context.get(key)
        if value is None or isinstance(value, (str, int, float, bool)):
            result[key] = value
    return result


def _issue_path(
    error_type: str,
    error: dict[str, object],
    message_args: Mapping[str, MessageArg],
) -> str:
    if error_type == "output_event_types_invalid":
        return "event_templates"
    if error_type in {
        "output_template_empty",
        "output_template_malformed",
        "output_template_unknown_variables",
    }:
        event_name = message_args.get("event_name")
        if isinstance(event_name, str) and event_name:
            return f"event_templates.{event_name}.template"
    return _path(error.get("loc", ()))


def report_from_validation_error(
    exc: ValidationError,
    *,
    stage: str,
    scope: str,
    owner_id: str = "",
    owner_name: str = "",
    owner_type: str = "",
) -> ValidationReport:
    issues = []
    for error in exc.errors(
        include_url=False,
        include_context=True,
        include_input=False,
    ):
        error_type = str(error.get("type", ""))
        message_args = _message_args(error_type, error)
        issues.append(
            ValidationIssue(
                code=_ERROR_CODES.get(error_type, "contract.invalid_value"),
                scope=scope,
                owner_id=owner_id,
                owner_name=owner_name,
                owner_type=owner_type,
                path=_issue_path(error_type, error, message_args),
                message=_safe_message(error),
                message_key=_ERROR_MESSAGE_KEYS.get(
                    error_type,
                    "validation.issue.contract.invalidValue",
                ),
                message_args=message_args,
            )
        )
    return ValidationReport(stage=stage, issues=tuple(issues))
