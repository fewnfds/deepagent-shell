from __future__ import annotations

import argparse
import importlib.metadata
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


APPLICATION_PACKAGE = "agent-shell-server"


@dataclass(frozen=True)
class Component:
    ecosystem: str
    name: str
    version: str
    declared_license: str
    source: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.ecosystem, self.name.casefold(), self.version


def _declared_license(raw: str | None, classifiers: Iterable[str] = ()) -> str:
    value = (raw or "").strip()
    if "\n" in value or len(value) > 160:
        value = ""
    aliases = {
        "apache 2.0": "Apache-2.0",
        "apache software license": "Apache-2.0",
        "bsd": "BSD-3-Clause",
        "bsd license": "BSD-3-Clause",
        "isc license": "ISC",
        "mit license": "MIT",
        "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
        "python software foundation license": "PSF-2.0",
        "the unlicense (unlicense)": "Unlicense",
    }
    if value:
        return aliases.get(value.casefold(), value)
    for classifier in classifiers:
        if classifier.startswith("License ::"):
            candidate = classifier.rsplit("::", 1)[-1].strip()
            return aliases.get(candidate.casefold(), candidate)
    return "NOASSERTION"


def _python_components(runtime_root: Path) -> list[Component]:
    python_home_text = (runtime_root / "python-home.txt").read_text(encoding="ascii").strip()
    python_home = (runtime_root / Path(python_home_text)).resolve()
    site_packages = python_home / "Lib" / "site-packages"
    if not (python_home / "python.exe").is_file() or not site_packages.is_dir():
        raise RuntimeError("The source runtime does not contain the expected Python layout.")

    components: list[Component] = []
    for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
        name = distribution.metadata.get("Name")
        if not name or name.casefold() == APPLICATION_PACKAGE:
            continue
        classifiers = distribution.metadata.get_all("Classifier") or ()
        license_value = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
        )
        source = (
            distribution.metadata.get("Home-page")
            or f"https://pypi.org/project/{name}/{distribution.version}/"
        )
        components.append(
            Component(
                ecosystem="pypi",
                name=name,
                version=distribution.version,
                declared_license=_declared_license(license_value, classifiers),
                source=source,
            )
        )

    components.append(
        Component(
            ecosystem="runtime",
            name="CPython",
            version=python_home.name.removeprefix("cpython-").split("-windows-", 1)[0],
            declared_license="PSF-2.0",
            source="https://www.python.org/",
        )
    )
    return components


def _npm_name(package_path: str) -> str:
    return package_path.rsplit("node_modules/", 1)[-1]


def _npm_components(frontend_root: Path) -> list[Component]:
    lock = json.loads((frontend_root / "package-lock.json").read_text(encoding="utf-8"))
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError("frontend/package-lock.json does not use the supported lockfile schema.")

    components: list[Component] = []
    for package_path, metadata in packages.items():
        if not package_path or not isinstance(metadata, dict) or metadata.get("dev") is True:
            continue
        version = metadata.get("version")
        if not isinstance(version, str) or not version:
            continue
        name = metadata.get("name") or _npm_name(package_path)
        if not isinstance(name, str) or not name:
            continue
        raw_license = metadata.get("license")
        if not isinstance(raw_license, str):
            raw_license = None
        source = metadata.get("resolved")
        if not isinstance(source, str) or not source:
            source = f"https://www.npmjs.com/package/{name}/v/{version}"
        components.append(
            Component(
                ecosystem="npm",
                name=name,
                version=version,
                declared_license=_declared_license(raw_license),
                source=source,
            )
        )
    return components


def _components(runtime_root: Path, frontend_root: Path) -> list[Component]:
    unique: dict[tuple[str, str, str], Component] = {}
    for component in [*_python_components(runtime_root), *_npm_components(frontend_root)]:
        unique.setdefault(component.key, component)
    return sorted(unique.values(), key=lambda item: item.key)


def _write_notices(path: Path, components: list[Component]) -> None:
    lines = [
        "# Third-party notices",
        "",
        "Agent Shell is licensed under the MIT License. Its runtime and compiled frontend use",
        "the components below. The declared-license column is generated from installed wheel",
        "metadata and `frontend/package-lock.json`; follow each source link for authoritative",
        "license and notice terms.",
        "",
        "| Ecosystem | Component | Version | Declared license | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for component in components:
        name = component.name.replace("|", "\\|")
        license_value = component.declared_license.replace("|", "\\|")
        lines.append(
            f"| {component.ecosystem} | {name} | {component.version} | "
            f"{license_value} | {component.source} |"
        )
    lines.extend(
        [
            "",
            "`NOASSERTION` means the upstream package metadata did not declare a short",
            "machine-readable license identifier; inspect its source link for the authoritative",
            "terms.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--frontend-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    components = _components(
        arguments.runtime_root.resolve(), arguments.frontend_root.resolve()
    )
    _write_notices(arguments.output.resolve(), components)
    print(f"Third-party notices generated for {len(components)} components.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
