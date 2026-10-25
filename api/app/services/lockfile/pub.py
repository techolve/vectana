import yaml


def parse_pubspec_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    data = yaml.safe_load(content) or {}
    result = []
    for name, info in (data.get("packages") or {}).items():
        # Only pub.dev packages are in OSV; skip sdk / git / path sources.
        if (info or {}).get("source") == "hosted" and info.get("version"):
            result.append((str(name), str(info["version"])))
    return "Pub", result
