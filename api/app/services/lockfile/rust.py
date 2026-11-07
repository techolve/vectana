import tomllib


def parse_cargo_lock(content: str) -> tuple[str, list[tuple[str, str]]]:
    data = tomllib.loads(content)
    result = []
    for pkg in data.get("package") or []:
        # Workspace members and path dependencies have no source; git
        # dependencies aren't on crates.io. Only registry crates are in OSV.
        if str(pkg.get("source", "")).startswith("registry+") and "version" in pkg:
            result.append((pkg["name"], pkg["version"]))
    return "crates.io", result
