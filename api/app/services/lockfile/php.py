import json


def parse_composer_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    data = json.loads(content)
    result = []
    for key in ("packages", "packages-dev"):
        for pkg in data.get(key) or []:
            name, version = pkg.get("name"), str(pkg.get("version") or "")
            # Branch checkouts ("dev-main") have no release to match against.
            if not name or not version or version.startswith("dev-"):
                continue
            if version[0] == "v" and version[1:2].isdigit():
                version = version[1:]
            result.append((name, version))
    return "Packagist", result
