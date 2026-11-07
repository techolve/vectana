def parse_gradle_lockfile(content: str) -> tuple[str, list[tuple[str, str]]]:
    """``group:artifact:version=configurations`` per line."""
    result = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("empty="):
            continue
        coords = line.split("=", 1)[0].split(":")
        if len(coords) == 3 and all(coords):
            result.append((f"{coords[0]}:{coords[1]}", coords[2]))
    return "Maven", result
