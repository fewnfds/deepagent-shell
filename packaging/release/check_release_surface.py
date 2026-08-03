from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


FORBIDDEN_PARTS = {
    ".agents",
    ".docs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
FORBIDDEN_NAMES = {".env", "AGENTS.md"}
ALLOWED_SOURCE_INSTRUCTION_FILES = {"frontend/AGENTS.md"}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".dump",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".sqlite",
    ".sqlite3",
}
TEXT_SUFFIXES = {
    ".bat",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}
PORTABLE_TOP_LEVEL = {
    ".env.example",
    "LICENSE",
    "README.md",
    "SBOM.spdx.json",
    "THIRD_PARTY_LICENSES",
    "THIRD_PARTY_NOTICES.md",
    "data",
    "docs",
    "release-manifest.json",
    "runtime",
    "start_server.bat",
}


def _tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    tracked: list[str] = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        path_text = item.decode("utf-8", errors="strict")
        if (repo_root / Path(path_text)).is_file():
            tracked.append(path_text)
    return tracked


def _path_issue(path_text: str) -> str | None:
    path = PurePosixPath(path_text)
    if (
        path.name in FORBIDDEN_NAMES
        and path_text not in ALLOWED_SOURCE_INSTRUCTION_FILES
    ):
        return "local-only file"
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return "generated or local-only directory"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return "generated data or credential-shaped file"
    if path.parts[:1] == ("data",):
        return "persistent user data"
    if path.parts[:1] == ("runtime",):
        return "runtime state"
    if path.parts[:1] == ("resources",):
        return "obsolete root resources directory"
    return None


def _checkout_reference_issues(
    content_root: Path, checkout_root: Path, tracked: list[str]
) -> list[str]:
    root_text = str(checkout_root.resolve())
    slash_root = root_text.replace("\\", "/")
    variants = {root_text, slash_root, f"file:///{slash_root}"}
    patterns = [re.compile(re.escape(value), re.IGNORECASE) for value in variants]
    issues: list[str] = []
    for path_text in tracked:
        path = content_root / Path(path_text)
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in patterns):
            issues.append(f"{path_text}: contains the current checkout path")
    return issues


def _portable_files(portable_root: Path) -> list[str]:
    return [
        path.relative_to(portable_root).as_posix()
        for path in portable_root.rglob("*")
        if path.is_file()
    ]


def _portable_path_issue(path_text: str) -> str | None:
    path = PurePosixPath(path_text)
    inside_python_runtime = path.parts[:3] == ("runtime", "app", "python")
    inside_site_packages = "site-packages" in path.parts
    is_python_ca_bundle = (
        inside_python_runtime
        and (
            (path.name == "cacert.pem" and "certifi" in path.parts)
            or path.parts[-4:] == ("grpc", "_cython", "_credentials", "roots.pem")
        )
    )
    if path.parts[0] not in PORTABLE_TOP_LEVEL:
        return "unexpected top-level release content"
    if path.name in {".env", "agent-shell.env"}:
        return "real settings file"
    forbidden_parts = {part for part in path.parts if part in FORBIDDEN_PARTS}
    if forbidden_parts and not (
        inside_python_runtime
        and not inside_site_packages
        and forbidden_parts <= {"__pycache__"}
    ):
        return "generated or local-only directory"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES and not (
        (
            inside_python_runtime
            and not inside_site_packages
            and path.suffix.lower() == ".pyc"
        )
        or is_python_ca_bundle
    ):
        return "generated data or credential-shaped file"
    if path.parts[:1] == ("data",):
        return "persistent user data"
    if path.parts[:2] in {
        ("runtime", "cache"),
        ("runtime", "tmp"),
        ("runtime", "home"),
    }:
        return "generated runtime state"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable-root", type=Path)
    arguments = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    if arguments.portable_root is not None:
        portable_root = arguments.portable_root.resolve()
        tracked = _portable_files(portable_root)
        issues = [
            f"{path_text}: {reason}"
            for path_text in tracked
            if (reason := _portable_path_issue(path_text)) is not None
        ]
        issues.extend(_checkout_reference_issues(portable_root, repo_root, tracked))
        label = "Portable release surface"
    else:
        tracked = _tracked_files(repo_root)
        issues = [
            f"{path_text}: {reason}"
            for path_text in tracked
            if (reason := _path_issue(path_text)) is not None
        ]
        issues.extend(_checkout_reference_issues(repo_root, repo_root, tracked))
        label = "Release surface"
    if issues:
        print(f"{label} check failed:", file=sys.stderr)
        for issue in sorted(issues):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"{label} check passed for {len(tracked)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
