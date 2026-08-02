from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


APPLICATION_NAME = "agent-shell"
APPLICATION_PACKAGE = "agent-shell-server"
LICENSE_FILE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")


@dataclass(frozen=True)
class Component:
    ecosystem: str
    name: str
    version: str
    declared_license: str
    source: str
    license_files: tuple[Path, ...] = ()

    @property
    def key(self) -> tuple[str, str, str]:
        return self.ecosystem, self.name.casefold(), self.version


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "component"


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


def _license_files(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    matches: list[Path] = []
    for child in directory.iterdir():
        upper_name = child.name.upper()
        if child.is_file() and any(upper_name.startswith(name) for name in LICENSE_FILE_NAMES):
            matches.append(child)
    return tuple(sorted(matches, key=lambda path: path.name.casefold()))


def _python_components(runtime_root: Path) -> tuple[list[Component], Path]:
    python_home_text = (runtime_root / "python-home.txt").read_text(encoding="ascii").strip()
    python_home = (runtime_root / Path(python_home_text)).resolve()
    site_packages = python_home / "Lib" / "site-packages"
    if not (python_home / "python.exe").is_file() or not site_packages.is_dir():
        raise RuntimeError("The portable runtime does not contain the expected Python layout.")

    components: list[Component] = []
    for distribution in importlib.metadata.distributions(path=[str(site_packages)]):
        name = distribution.metadata.get("Name")
        if not name or name.casefold() == APPLICATION_PACKAGE:
            continue
        classifiers = distribution.metadata.get_all("Classifier") or ()
        license_value = distribution.metadata.get("License-Expression") or distribution.metadata.get("License")
        source = distribution.metadata.get("Home-page") or f"https://pypi.org/project/{name}/{distribution.version}/"
        files: list[Path] = []
        for relative in distribution.files or ():
            upper_name = Path(str(relative)).name.upper()
            if not any(upper_name.startswith(candidate) for candidate in LICENSE_FILE_NAMES):
                continue
            located = Path(distribution.locate_file(relative))
            if located.is_file():
                files.append(located)
        components.append(
            Component(
                ecosystem="pypi",
                name=name,
                version=distribution.version,
                declared_license=_declared_license(license_value, classifiers),
                source=source,
                license_files=tuple(sorted(set(files), key=lambda path: str(path).casefold())),
            )
        )

    python_license_files = _license_files(python_home)
    components.append(
        Component(
            ecosystem="runtime",
            name="CPython",
            version=python_home.name.removeprefix("cpython-").split("-windows-", 1)[0],
            declared_license="PSF-2.0",
            source="https://www.python.org/",
            license_files=python_license_files,
        )
    )
    return components, site_packages


def _npm_name(package_path: str) -> str:
    return package_path.rsplit("node_modules/", 1)[-1]


def _npm_components(frontend_root: Path) -> list[Component]:
    lock_path = frontend_root / "package-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
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
        package_directory = frontend_root / Path(package_path)
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
                license_files=_license_files(package_directory),
            )
        )
    return components


def _components(runtime_root: Path, frontend_root: Path) -> list[Component]:
    python, _ = _python_components(runtime_root)
    unique: dict[tuple[str, str, str], Component] = {}
    for component in [*python, *_npm_components(frontend_root)]:
        unique.setdefault(component.key, component)
    return sorted(unique.values(), key=lambda item: item.key)


def _write_notices(path: Path, components: list[Component]) -> None:
    lines = [
        "# Third-party notices",
        "",
        "Agent Shell is licensed under the MIT License. The release also contains the",
        "components below. The declared-license column is generated from installed wheel",
        "metadata and `frontend/package-lock.json`; original license and notice files are",
        "included in release archives under `THIRD_PARTY_LICENSES/` when supplied upstream.",
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
            "machine-readable license identifier; inspect its bundled license files and source",
            "link for the authoritative terms.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _spdx_id(component: Component) -> str:
    digest = hashlib.sha256("\0".join(component.key).encode("utf-8")).hexdigest()[:12]
    return f"SPDXRef-{_safe_name(component.ecosystem)}-{_safe_name(component.name)}-{digest}"


def _write_sbom(path: Path, components: list[Component], version: str) -> None:
    package_rows = [
        {
            "SPDXID": "SPDXRef-Package-Agent-Shell",
            "name": APPLICATION_NAME,
            "versionInfo": version,
            "downloadLocation": "https://github.com/fewnfds/agent-shell",
            "filesAnalyzed": False,
            "licenseConcluded": "MIT",
            "licenseDeclared": "MIT",
            "copyrightText": "NOASSERTION",
        }
    ]
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-Agent-Shell",
        }
    ]
    for component in components:
        spdx_id = _spdx_id(component)
        package_rows.append(
            {
                "SPDXID": spdx_id,
                "name": component.name,
                "versionInfo": component.version,
                "downloadLocation": component.source,
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": component.declared_license,
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": (
                            f"pkg:{component.ecosystem}/{component.name}@{component.version}"
                        ),
                    }
                ],
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-Agent-Shell",
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id,
            }
        )
    digest = hashlib.sha256(
        json.dumps(package_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"agent-shell-{version}-windows-x64",
        "documentNamespace": f"https://github.com/fewnfds/agent-shell/sbom/{digest}",
        "creationInfo": {
            "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "creators": ["Tool: agent-shell-generate-release-metadata"],
        },
        "packages": package_rows,
        "relationships": relationships,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_license_files(root: Path, components: list[Component]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for component in components:
        if not component.license_files:
            continue
        destination = root / component.ecosystem / f"{_safe_name(component.name)}-{_safe_name(component.version)}"
        destination.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        for index, source in enumerate(component.license_files, start=1):
            name = source.name
            if name.casefold() in used_names:
                name = f"{index}-{name}"
            used_names.add(name.casefold())
            shutil.copy2(source, destination / name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--frontend-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--notices", required=True, type=Path)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--licenses", type=Path)
    arguments = parser.parse_args()

    components = _components(arguments.runtime_root.resolve(), arguments.frontend_root.resolve())
    _write_notices(arguments.notices.resolve(), components)
    if arguments.sbom is not None:
        _write_sbom(arguments.sbom.resolve(), components, arguments.version)
    if arguments.licenses is not None:
        _copy_license_files(arguments.licenses.resolve(), components)
    print(f"Release metadata generated for {len(components)} third-party components.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
