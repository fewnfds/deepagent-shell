from __future__ import annotations

import ast
from pathlib import Path

from agent_shell.registries.errors import ResourceScanError


MAX_MIDDLEWARE_SOURCE_LENGTH = 100_000


def _target_binds_middleware(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return target.id == "middleware"
    if isinstance(target, (ast.List, ast.Tuple)):
        return any(_target_binds_middleware(item) for item in target.elts)
    if isinstance(target, ast.Starred):
        return _target_binds_middleware(target.value)
    return False


def _binds_middleware(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return any(_target_binds_middleware(target) for target in node.targets)
    if isinstance(node, ast.AnnAssign):
        return _target_binds_middleware(node.target)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == "middleware"
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any(
            (alias.asname or alias.name.split(".", 1)[0]) == "middleware"
            for alias in node.names
        )
    return False


def validate_middleware_source(source: str) -> ast.Module:
    if len(source) > MAX_MIDDLEWARE_SOURCE_LENGTH:
        raise ResourceScanError(
            "resource.error.customMiddleware.sourceTooLong",
            (
                "Middleware construction source must contain at most "
                f"{MAX_MIDDLEWARE_SOURCE_LENGTH} characters."
            ),
            {"max_length": MAX_MIDDLEWARE_SOURCE_LENGTH},
        )
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        line = exc.lineno or 1
        raise ResourceScanError(
            "resource.error.customMiddleware.syntax",
            f"The middleware source contains a Python syntax error on line {line}.",
            {"line": line},
        ) from None
    if not any(_binds_middleware(node) for node in tree.body):
        raise ResourceScanError(
            "resource.error.customMiddleware.bindingRequired",
            "Middleware construction source must bind middleware at module level.",
        )
    return tree


def scan_custom_middlewares(
    directory: Path,
) -> dict:
    catalog: list[dict] = []
    errors: dict[str, dict[str, object]] = {}
    candidates = directory.glob("*.py") if directory.exists() else ()
    for path in sorted(candidates, key=lambda item: item.stem.lower()):
        if path.name == "__init__.py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            errors[path.name] = ResourceScanError(
                "resource.error.customMiddleware.readFailed",
                "The Python middleware recipe could not be read.",
            ).as_dict()
            continue
        except UnicodeError:
            errors[path.name] = ResourceScanError(
                "resource.error.customMiddleware.invalidEncoding",
                "The Python middleware recipe must use UTF-8 encoding.",
            ).as_dict()
            continue
        try:
            tree = validate_middleware_source(source)
        except ResourceScanError as exc:
            errors[path.name] = exc.as_dict()
            continue

        docstring = ast.get_docstring(tree) or ""
        description = docstring.splitlines()[0].strip() if docstring else ""
        catalog.append(
            {
                "name": path.stem,
                "filename": path.name,
                "description": description,
                "source": source,
            }
        )

    return {"catalog": catalog, "errors": errors}
