def parse_obsinfo(content: str) -> str | None:
    """Parses simple key: value format from .obsinfo file."""
    for line in content.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                key, value = parts
                if key.strip() == "version":
                    return value.strip()
    return None


def parse_spec(content: str) -> tuple[str, str]:
    """Parses version and release from a .spec file."""
    version = ""
    release = ""
    for line in content.splitlines():
        line_lower = line.lower()
        if line_lower.startswith("version:"):
            try:
                version = line.split(":", 1)[1].strip()
            except IndexError:
                pass
        elif line_lower.startswith("release:"):
            try:
                release = line.split(":", 1)[1].strip()
            except IndexError:
                pass
    return version, release
