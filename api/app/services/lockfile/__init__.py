"""Lockfile parsers. Each returns (ecosystem, [(name, version), ...])."""

from collections.abc import Callable

from app.services.lockfile import npm, pub, python

Parsed = tuple[str, list[tuple[str, str]]]

PARSERS: dict[str, Callable[[str], Parsed]] = {
    "package-lock.json": npm.parse_package_lock,
    "npm-shrinkwrap.json": npm.parse_package_lock,
    "pnpm-lock.yaml": npm.parse_pnpm_lock,
    "uv.lock": python.parse_uv_lock,
    "poetry.lock": python.parse_poetry_lock,
    "requirements.txt": python.parse_requirements,
    "pubspec.lock": pub.parse_pubspec_lock,
}


class UnsupportedLockfile(ValueError):
    pass


def parse(filename: str, content: str) -> Parsed:
    base = filename.rsplit("/", 1)[-1]
    parser = PARSERS.get(base)
    if parser is None and base.endswith(".txt") and "requirements" in base:
        parser = python.parse_requirements
    if parser is None:
        raise UnsupportedLockfile(f"Unsupported file {base!r}. Supported: {', '.join(PARSERS)}")
    ecosystem, packages = parser(content)
    return ecosystem, sorted(set(packages))
