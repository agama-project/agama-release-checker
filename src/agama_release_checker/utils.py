import datetime
import logging
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

    Requires ISO 8601 format with timezone information.
    Examples of accepted input:
    - 2025-03-04 11:47:33 +0200
    - 2026-02-03T09:27:06Z
    """
    if not ts_str or ts_str == "Unknown":
        return "Unknown"

    try:
        dt = datetime.datetime.fromisoformat(ts_str.strip())

        if dt.tzinfo is None:
            logging.error(f"Timestamp is missing timezone information: {ts_str}")
            return "Unknown"

        # Convert to target timezone
        dt_localized = dt.astimezone(REPORT_TIMEZONE)

        return dt_localized.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        logging.error(f"Invalid timestamp format: {ts_str}")
        return "Unknown"
