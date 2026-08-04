from __future__ import annotations

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
    repo_root: Path, tracked: list[str]
) -> list[str]:
    root_text = str(repo_root.resolve())
    slash_root = root_text.replace("\\", "/")
    variants = {root_text, slash_root, f"file:///{slash_root}"}
    patterns = [re.compile(re.escape(value), re.IGNORECASE) for value in variants]
    issues: list[str] = []
    for path_text in tracked:
        path = repo_root / Path(path_text)
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(content) for pattern in patterns):
            issues.append(f"{path_text}: contains the current checkout path")
    return issues


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    tracked = _tracked_files(repo_root)
    issues = [
        f"{path_text}: {reason}"
        for path_text in tracked
        if (reason := _path_issue(path_text)) is not None
    ]
    issues.extend(_checkout_reference_issues(repo_root, tracked))
    if issues:
        print("Release surface check failed:", file=sys.stderr)
        for issue in sorted(issues):
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"Release surface check passed for {len(tracked)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
