"""SBOM parsing: CycloneDX (JSON / XML) and SPDX (JSON / tag-value).

Components are identified by their package URL (purl), which maps onto an OSV
ecosystem. Anything without a purl, or of a type OSV can't be queried for here
(OS packages, containers, GitHub Actions, ...), is counted as unsupported.
"""

import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree

CYCLONEDX = "CycloneDX"
SPDX = "SPDX"

# purl type -> OSV ecosystem
PURL_ECOSYSTEMS = {
    "npm": "npm",
    "pypi": "PyPI",
    "maven": "Maven",
    "golang": "Go",
    "cargo": "crates.io",
    "composer": "Packagist",
    "gem": "RubyGems",
    "nuget": "NuGet",
    "pub": "Pub",
}

NO_PURL = "(no purl)"


@dataclass
class Sbom:
    format: str  # CYCLONEDX | SPDX
    packages: list[tuple[str, str, str]]  # (ecosystem, name, version)
    # purl type (or NO_PURL) -> number of components that were left out
    unsupported: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Purl:
    type: str
    namespace: str | None
    name: str
    version: str | None


_PURL = re.compile(r"^pkg:/*(?P<type>[A-Za-z0-9.+-]+)/(?P<path>[^@?#]+)(?:@(?P<version>[^?#]+))?")


def parse_purl(purl: str) -> Purl | None:
    m = _PURL.match(purl.strip())
    if not m:
        return None
    segments = [unquote(s) for s in m.group("path").strip("/").split("/") if s]
    if not segments:
        return None
    version = m.group("version")
    return Purl(
        type=m.group("type").lower(),
        namespace="/".join(segments[:-1]) or None,
        name=segments[-1],
        version=unquote(version) if version else None,
    )


def to_package(purl: Purl) -> tuple[str, str, str] | None:
    """(ecosystem, name, version) as OSV expects them, or None."""
    ecosystem = PURL_ECOSYSTEMS.get(purl.type)
    if ecosystem is None or not purl.version:
        return None
    version = purl.version
    if purl.type == "maven":
        if not purl.namespace:
            return None
        name = f"{purl.namespace}:{purl.name}"
    elif purl.type in ("npm", "golang", "composer"):
        name = f"{purl.namespace}/{purl.name}" if purl.namespace else purl.name
    else:
        name = purl.name
    if purl.type == "golang" and version.startswith("v"):
        version = version[1:]
    return ecosystem, name, version


def detect(content: str) -> str | None:
    """CYCLONEDX, SPDX, or None if this doesn't look like an SBOM."""
    head = content.lstrip("﻿ \t\r\n")[:4096]
    if head.startswith("{"):
        if re.search(r'"bomFormat"\s*:\s*"CycloneDX"', head):
            return CYCLONEDX
        if re.search(r'"spdxVersion"\s*:', head):
            return SPDX
        # Keys may come in any order; fall back to a full parse.
        try:
            data = json.loads(content)
        except ValueError:
            return None
        if isinstance(data, dict):
            if data.get("bomFormat") == "CycloneDX":
                return CYCLONEDX
            if "spdxVersion" in data:
                return SPDX
        return None
    if head.startswith("<"):
        return CYCLONEDX if "cyclonedx.org/schema/bom" in head else None
    if re.search(r"^SPDXVersion:", head, re.MULTILINE):
        return SPDX
    return None


def parse(content: str) -> Sbom:
    fmt = detect(content)
    text = content.lstrip("﻿ \t\r\n")
    if fmt == CYCLONEDX:
        purls = _cyclonedx_xml(text) if text.startswith("<") else _cyclonedx_json(text)
    elif fmt == SPDX:
        purls = _spdx_json(text) if text.startswith("{") else _spdx_tag_value(text)
    else:
        raise ValueError("Not a CycloneDX or SPDX document")
    return _collect(fmt, purls)


def _collect(fmt: str, purls: Iterable[str | None]) -> Sbom:
    packages: set[tuple[str, str, str]] = set()
    unsupported: Counter[str] = Counter()
    for raw in purls:
        purl = parse_purl(raw) if raw else None
        if purl is None:
            unsupported[NO_PURL] += 1
            continue
        pkg = to_package(purl)
        if pkg is None:
            unsupported[purl.type] += 1
        else:
            packages.add(pkg)
    return Sbom(format=fmt, packages=sorted(packages), unsupported=dict(unsupported))


# --- CycloneDX ---------------------------------------------------------------


def _cyclonedx_json(text: str) -> Iterator[str | None]:
    data = json.loads(text)

    def walk(components: list[dict[str, Any]]) -> Iterator[str | None]:
        for c in components or []:
            if not isinstance(c, dict):
                continue
            # The subject itself is in metadata.component, not here, so every
            # entry is a dependency.
            yield c.get("purl")
            yield from walk(c.get("components") or [])

    yield from walk(data.get("components") or [])


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _cyclonedx_xml(text: str) -> Iterator[str | None]:
    # Entity expansion is the classic XML attack; SBOMs never need a DTD.
    if re.search(r"<!(DOCTYPE|ENTITY)", text[:65536], re.IGNORECASE):
        raise ValueError("DTDs are not allowed in SBOM XML")
    root = ElementTree.fromstring(text)

    def walk(container: ElementTree.Element) -> Iterator[str | None]:
        for comp in container:
            if _local(comp.tag) != "component":
                continue
            purl = next((c.text for c in comp if _local(c.tag) == "purl"), None)
            yield purl.strip() if purl else None
            for child in comp:
                if _local(child.tag) == "components":
                    yield from walk(child)

    for child in root:
        if _local(child.tag) == "components":
            yield from walk(child)


# --- SPDX --------------------------------------------------------------------

_DOCUMENT = "SPDXRef-DOCUMENT"


def _spdx_json(text: str) -> Iterator[str | None]:
    data = json.loads(text)
    described = set(data.get("documentDescribes") or [])
    for rel in data.get("relationships") or []:
        if rel.get("spdxElementId") == _DOCUMENT and rel.get("relationshipType") == "DESCRIBES":
            described.add(rel.get("relatedSpdxElement"))
    for pkg in data.get("packages") or []:
        if pkg.get("SPDXID") in described:
            continue
        purls: list[str | None] = [
            ref.get("referenceLocator")
            for ref in pkg.get("externalRefs") or []
            if ref.get("referenceType") == "purl"
        ]
        yield from purls or [None]


def _spdx_tag_value(text: str) -> Iterator[str | None]:
    packages: dict[str, list[str]] = {}
    described: set[str] = set()
    current: list[str] | None = None
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key == "PackageName":
            current = []
        elif key == "SPDXID" and current is not None:
            packages[value] = current
        elif key == "ExternalRef" and current is not None:
            parts = value.split()
            if len(parts) >= 3 and parts[1] == "purl":
                current.append(parts[2])
        elif key == "Relationship":
            parts = value.split()
            if len(parts) == 3 and parts[0] == _DOCUMENT and parts[1] == "DESCRIBES":
                described.add(parts[2])
        elif key in ("FileName", "SnippetSPDXID"):
            current = None
    for spdx_id, purls in packages.items():
        if spdx_id in described:
            continue
        if purls:
            yield from purls
        else:
            yield None
