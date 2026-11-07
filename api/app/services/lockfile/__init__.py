"""Dependency file parsers: lockfiles (picked by filename) and SBOMs (picked by
content). ``parse`` returns every package as (ecosystem, name, version)."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.services import sbom
from app.services.lockfile import go, jvm, npm, php, pub, python, rust

Parsed = tuple[str, list[tuple[str, str]]]

PARSERS: dict[str, Callable[[str], Parsed]] = {
    "package-lock.json": npm.parse_package_lock,
    "npm-shrinkwrap.json": npm.parse_package_lock,
    "pnpm-lock.yaml": npm.parse_pnpm_lock,
    "uv.lock": python.parse_uv_lock,
    "poetry.lock": python.parse_poetry_lock,
    "requirements.txt": python.parse_requirements,
    "pubspec.lock": pub.parse_pubspec_lock,
    "go.mod": go.parse_go_mod,
    "go.sum": go.parse_go_sum,
    "composer.lock": php.parse_composer_lock,
    "Cargo.lock": rust.parse_cargo_lock,
    "gradle.lockfile": jvm.parse_gradle_lockfile,
}


class UnsupportedLockfile(ValueError):
    pass


@dataclass
class ParseResult:
    kind: str  # "lockfile" | "sbom"
    format: str  # lockfile ecosystem, or "CycloneDX" / "SPDX"
    packages: list[tuple[str, str, str]]
    unsupported: dict[str, int] = field(default_factory=dict)

    @property
    def ecosystems(self) -> list[str]:
        return sorted({eco for eco, _, _ in self.packages})


def _lockfile_parser(base: str) -> Callable[[str], Parsed] | None:
    parser = PARSERS.get(base)
    if parser is None and base.endswith(".txt") and "requirements" in base:
        parser = python.parse_requirements
    if parser is None and base.endswith("gradle.lockfile"):
        parser = jvm.parse_gradle_lockfile  # e.g. buildscript-gradle.lockfile
    return parser


def parse(filename: str, content: str) -> ParseResult:
    base = filename.rsplit("/", 1)[-1]
    parser = _lockfile_parser(base)
    if parser is not None:
        ecosystem, packages = parser(content)
        triples = sorted({(ecosystem, name, version) for name, version in packages})
        return ParseResult(kind="lockfile", format=ecosystem, packages=triples)
    if sbom.detect(content):
        doc = sbom.parse(content)
        return ParseResult(
            kind="sbom", format=doc.format, packages=doc.packages, unsupported=doc.unsupported
        )
    raise UnsupportedLockfile(
        f"Unsupported file {base!r}. Supported: {', '.join(PARSERS)}, CycloneDX / SPDX SBOM"
    )
