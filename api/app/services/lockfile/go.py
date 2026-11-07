"""Go modules. OSV's Go ecosystem expects versions without the leading "v"."""

import re


def _version(v: str) -> str:
    return v[1:] if v.startswith("v") else v


_REQUIRE_LINE = re.compile(r"^\s*(\S+)\s+(v\S+)")
_REPLACE = re.compile(r"^\s*(\S+)(?:\s+(v\S+))?\s*=>\s*(\S+)(?:\s+(v\S+))?")


def _strip_comment(line: str) -> str:
    return line.split("//", 1)[0].rstrip()


def parse_go_mod(content: str) -> tuple[str, list[tuple[str, str]]]:
    """``require`` directives (Go 1.17+ lists indirect dependencies too),
    with ``replace`` directives applied. Local path replacements are dropped."""
    requires: list[tuple[str, str]] = []
    replaces: list[tuple[str, str | None, str, str | None]] = []
    block: str | None = None
    for raw in content.splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if block is not None:
            if line == ")":
                block = None
                continue
            directive, body = block, line
        else:
            directive, _, body = line.partition(" ")
            body = body.strip()
            if body == "(":
                block = directive
                continue
        if directive == "require" and (m := _REQUIRE_LINE.match(body)):
            requires.append((m.group(1), m.group(2)))
        elif directive == "replace" and (r := _REPLACE.match(body)):
            replaces.append((r.group(1), r.group(2), r.group(3), r.group(4)))

    result: list[tuple[str, str]] = []
    for name, version in requires:
        target: tuple[str, str] | None = (name, version)
        for old, old_ver, new, new_ver in replaces:
            if old == name and (old_ver is None or old_ver == version):
                # "=> ../local" has no version: it's not a published module.
                target = (new, new_ver) if new_ver else None
                break
        if target:
            result.append((target[0], _version(target[1])))
    return "Go", result


def parse_go_sum(content: str) -> tuple[str, list[tuple[str, str]]]:
    """Every module whose source was downloaded. Can include versions that
    minimal version selection no longer uses, so go.mod is more precise."""
    result = []
    for line in content.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[1].endswith("/go.mod"):
            continue
        result.append((parts[0], _version(parts[1])))
    return "Go", result
