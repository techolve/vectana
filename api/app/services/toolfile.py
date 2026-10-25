"""Tool version files (mise.toml, .tool-versions) -> EOL runtimes.

These list languages and tools rather than packages, so they are imported as
runtimes and checked against endoflife.date (not OSV).
"""

import re
import tomllib
from dataclasses import dataclass
from typing import Any

TOOL_FILES = ("mise.toml", ".mise.toml", "mise.local.toml", ".tool-versions")

# mise/asdf names that differ from endoflife.date product names or aliases.
EXTRA_ALIASES = {
    "kubectl": "kubernetes",
    "golang": "go",
}
# mise's java versions carry the vendor: "temurin-21.0.2", "corretto-17".
JAVA_VENDORS = {
    "temurin": "eclipse-temurin",
    "adoptopenjdk": "eclipse-temurin",
    "corretto": "amazon-corretto",
    "zulu": "azul-zulu",
    "oracle": "oracle-jdk",
    "microsoft": "microsoft-build-of-openjdk",
    "liberica": "bellsoft-liberica",
    "semeru": "ibm-semeru-runtime",
    "sapmachine": "sapmachine",
}

_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class Entry:
    tool: str
    version: str


@dataclass(frozen=True)
class Resolved:
    tool: str
    version: str
    product: str | None
    reason: str | None  # why it was skipped, when product is None


def is_tool_file(filename: str) -> bool:
    return filename.rsplit("/", 1)[-1] in TOOL_FILES


def _versions(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for item in value for v in _versions(item)]
    if isinstance(value, dict) and "version" in value:
        return _versions(value["version"])
    return []


def parse_mise(content: str) -> list[Entry]:
    tools = tomllib.loads(content).get("tools") or {}
    return [Entry(str(tool), v) for tool, value in tools.items() for v in _versions(value)]


def parse_tool_versions(content: str) -> list[Entry]:
    entries = []
    for line in content.splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) >= 2:
            entries += [Entry(parts[0], v) for v in parts[1:]]
    return entries


def parse(filename: str, content: str) -> list[Entry]:
    base = filename.rsplit("/", 1)[-1]
    return parse_tool_versions(content) if base == ".tool-versions" else parse_mise(content)


def product_index(products: list[dict[str, Any]]) -> dict[str, str]:
    """name/alias (lowercase) -> endoflife.date product name."""
    index: dict[str, str] = {}
    for p in products:
        for name in [p.get("name", ""), *(p.get("aliases") or [])]:
            index.setdefault(str(name).lower(), p["name"])
    for alias, product in EXTRA_ALIASES.items():
        index.setdefault(alias, product)
    return index


def resolve(entry: Entry, index: dict[str, str]) -> Resolved:
    # Backend prefixes: "aqua:hashicorp/terraform", "core:python" -> "terraform", "python".
    tool = entry.tool.lower().split(":")[-1].rsplit("/", 1)[-1]
    version = entry.version.strip().removeprefix("prefix:")

    if tool == "java":
        vendor, _, rest = version.partition("-")
        product = JAVA_VENDORS.get(vendor) if rest else None
        if product is None:
            return Resolved(entry.tool, entry.version, None, "unsupported")
        tool_product: str | None = product
        version = rest
    else:
        tool_product = index.get(tool)
        if tool_product is None:
            return Resolved(entry.tool, entry.version, None, "unsupported")

    match = _VERSION.match(version)
    if match is None:  # "lts", "latest", "system", "ref:main"…
        return Resolved(entry.tool, entry.version, None, "unpinned")
    return Resolved(entry.tool, match.group(1), tool_product, None)
