import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CACHE_DIR = Path.home() / ".cache" / "agama-release-checker"

# Default timezone, can be overridden by main.py
REPORT_TIMEZONE = ZoneInfo("Europe/Berlin")


def ensure_dir(path: Path) -> None:
    """Creates the directory if it doesn't already exist."""
    path.mkdir(parents=True, exist_ok=True)


def format_timestamp(ts_str: str | None) -> str:
    """Parses a timestamp string and formats it according to REPORT_TIMEZONE.

    Handles formats like:
    - 2025-02-18 10:48:42 (assumed UTC if no TZ)
    - 2025-03-04 11:47:33 +0200
    - ISO 8601
    """
    if not ts_str or ts_str == "Unknown":
        return "Unknown"

    try:
        # Try to parse with fromisoformat (handles most common formats in 3.11+)
        # If it has a space but no T, fromisoformat might still work in 3.11+
        dt = datetime.datetime.fromisoformat(ts_str.strip())

        # If it's naive, assume UTC (common for OBS/Gitea if not specified)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)

        # Convert to target timezone
        dt_localized = dt.astimezone(REPORT_TIMEZONE)

        return dt_localized.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts_str
