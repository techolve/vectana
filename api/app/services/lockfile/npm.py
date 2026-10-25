import json
import re

import yaml


def parse_package_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    data = json.loads(content)
    result: list[tuple[str, str]] = []
    packages = data.get("packages")
    if isinstance(packages, dict):  # lockfileVersion 2 / 3
        for path, info in packages.items():
            if not path or info.get("link") or "version" not in info:
                continue
            name = info.get("name") or path.rsplit("node_modules/", 1)[-1]
            result.append((name, info["version"]))
    else:  # lockfileVersion 1

        def walk(deps: dict[str, dict]) -> None:  # type: ignore[type-arg]
            for name, info in deps.items():
                if "version" in info and not str(info["version"]).startswith("file:"):
                    result.append((name, info["version"]))
                walk(info.get("dependencies") or {})

        walk(data.get("dependencies") or {})
    return "npm", result


_PEER_SUFFIX = re.compile(r"\(.*\)$")


def parse_pnpm_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    data = yaml.safe_load(content) or {}
    result: list[tuple[str, str]] = []
    for key in (data.get("packages") or {}).keys():
        spec = _PEER_SUFFIX.sub("", str(key)).lstrip("/")
        # v6 used "name/1.2.3"; v9 uses "name@1.2.3". Scoped names start with "@".
        at = spec.rfind("@")
        if at > 0:
            name, version = spec[:at], spec[at + 1 :]
        elif "/" in spec:
            name, _, version = spec.rpartition("/")
        else:
            continue
        if name and version and version[0].isdigit():
            result.append((name, version))
    return "npm", result
