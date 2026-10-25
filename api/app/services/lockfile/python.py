import re
import tomllib


def _toml_packages(content: str, skip_local: bool) -> list[tuple[str, str]]:
    data = tomllib.loads(content)
    result = []
    for pkg in data.get("package") or []:
        source = pkg.get("source") or {}
        if skip_local and ("virtual" in source or "editable" in source or "directory" in source):
            continue
        if "name" in pkg and "version" in pkg:
            result.append((pkg["name"], pkg["version"]))
    return result


def parse_uv_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    return "PyPI", _toml_packages(content, skip_local=True)


def parse_poetry_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    return "PyPI", _toml_packages(content, skip_local=False)


_PINNED = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;#]+)")


def parse_requirements(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Only exact pins (``name==version``) can be matched against OSV."""
    result = []
    for line in content.splitlines():
        m = _PINNED.match(line)
        if m:
            result.append((m.group(1), m.group(2)))
    return "PyPI", result
