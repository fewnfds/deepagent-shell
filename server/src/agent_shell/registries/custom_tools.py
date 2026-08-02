from __future__ import annotations

import ast
import re
from pathlib import Path

from agent_shell.registries.errors import ResourceScanError


CUSTOM_TOOL_RESOURCE_NAME_PATTERN = r"^[A-Za-z_][A-Za-z0-9_-]*$"
CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH = 120


def _custom_tool_resource_name_error(value: str) -> ResourceScanError | None:
    if (
        not value
        or len(value) > CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH
        or re.fullmatch(CUSTOM_TOOL_RESOURCE_NAME_PATTERN, value) is None
    ):
        return ResourceScanError(
            "resource.error.customTool.invalidName",
            (
                "The filename stem must start with an ASCII letter or underscore, "
                "contain only ASCII letters, digits, underscores, and hyphens, and "
                f"contain at most {CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH} characters."
            ),
            {"max_length": CUSTOM_TOOL_RESOURCE_NAME_MAX_LENGTH},
        )
    return None


def custom_tool_resource_name_issue(value: str) -> str:
    issue = _custom_tool_resource_name_error(value)
    return str(issue) if issue is not None else ""


def _tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.expr | None:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "tool":
            return decorator
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            return decorator
    return None


def _decorator_keyword(decorator: ast.expr, name: str) -> ast.expr | None:
    if not isinstance(decorator, ast.Call):
        return None
    return next(
        (keyword.value for keyword in decorator.keywords if keyword.arg == name),
        None,
    )


def _has_decorator_keyword(decorator: ast.expr, name: str) -> bool:
    value = _decorator_keyword(decorator, name)
    if value is None:
        return False
    if not isinstance(value, ast.Constant):
        return True
    if name == "description":
        return isinstance(value.value, str) and bool(value.value.strip())
    return value.value is not None


def _tool_description(decorator: ast.expr, docstring: str) -> str:
    if docstring:
        return docstring.splitlines()[0].strip()
    value = _decorator_keyword(decorator, "description")
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value.strip().splitlines()[0]
    return "Provided by @tool(description=...)."


def _tool_runtime_name(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.expr,
) -> str | None:
    if not isinstance(decorator, ast.Call):
        return node.name
    if decorator.args:
        explicit = decorator.args[0]
        if isinstance(explicit, ast.Constant) and isinstance(explicit.value, str):
            return explicit.value
        return None
    explicit = _decorator_keyword(decorator, "name_or_callable")
    if explicit is None:
        return node.name
    if isinstance(explicit, ast.Constant) and isinstance(explicit.value, str):
        return explicit.value
    return None


def _missing_parameter_annotations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    if node.args.vararg is not None:
        parameters.append(node.args.vararg)
    if node.args.kwarg is not None:
        parameters.append(node.args.kwarg)
    return [parameter.arg for parameter in parameters if parameter.annotation is None]


def scan_custom_tool_file(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ResourceScanError(
            "resource.error.customTool.readFailed",
            "The Python tool file could not be read.",
        ) from exc
    except UnicodeError as exc:
        raise ResourceScanError(
            "resource.error.customTool.invalidEncoding",
            "The Python tool file must use UTF-8 encoding.",
        ) from exc
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        line = exc.lineno or 1
        raise ResourceScanError(
            "resource.error.customTool.syntax",
            f"The Python tool file contains a syntax error on line {line}.",
            {"line": line},
        ) from exc

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorator = _tool_decorator(node)
        if decorator is None:
            continue
        docstring = ast.get_docstring(node) or ""
        if not docstring and not _has_decorator_keyword(decorator, "description"):
            raise ResourceScanError(
                "resource.error.customTool.descriptionRequired",
                (
                    f"@tool function {node.name} must provide a docstring or an "
                    "explicit description."
                ),
                {"function_name": node.name},
            )
        if not _has_decorator_keyword(decorator, "args_schema"):
            missing = _missing_parameter_annotations(node)
            if missing:
                parameter_names = ", ".join(missing)
                raise ResourceScanError(
                    "resource.error.customTool.parameterAnnotationsRequired",
                    (
                        f"@tool function {node.name} has parameters without type "
                        f"annotations: {parameter_names}."
                    ),
                    {
                        "function_name": node.name,
                        "parameter_names": parameter_names,
                    },
                )
        return {
            "name": path.stem,
            "function": node.name,
            "tool_name": _tool_runtime_name(node, decorator),
            "description": _tool_description(decorator, docstring),
            "filename": path.name,
        }
    raise ResourceScanError(
        "resource.error.customTool.decoratedFunctionRequired",
        "No module-level function decorated with @tool was found.",
    )


def resolve_custom_tool_file(
    resource_name: str,
    directory: Path,
) -> Path | None:
    issue = _custom_tool_resource_name_error(resource_name)
    if issue is not None:
        raise issue

    path = directory / f"{resource_name}.py"
    return path if path.is_file() else None


def scan_custom_tools(
    directory: Path,
) -> dict:
    catalog: list[dict] = []
    errors: dict[str, dict[str, object]] = {}
    candidates = directory.glob("*.py") if directory.exists() else ()
    for path in sorted(candidates, key=lambda item: item.stem.lower()):
        issue = _custom_tool_resource_name_error(path.stem)
        if issue is not None:
            errors[path.name] = issue.as_dict()
            continue
        try:
            metadata = scan_custom_tool_file(path)
            catalog.append(metadata)
        except ResourceScanError as exc:
            errors[path.name] = exc.as_dict()
    return {"catalog": catalog, "errors": errors}
