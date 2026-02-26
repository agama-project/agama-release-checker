import logging
import re
import subprocess
import time
from pathlib import Path

from .utils import ensure_dir


def _sanitize_filename(s: str) -> str:
    """Replaces non-alphanumeric characters with underscores."""
    return re.sub(r"[^a-zA-Z0-9_\-.]", "_", s)


def _generate_cache_filename(cmd: list[str]) -> str:
    """Generates a readable cache filename from the command arguments."""
    # Skip 'osc' prefix if present for cleaner names, or keep it?
    # Keeping it is safer for uniqueness if we ever run other commands.
    parts = [_sanitize_filename(arg) for arg in cmd]
    return "_".join(parts) + ".txt"


def run_cached_command(
    cmd: list[str],
    cache_dir: Path | None = None,
    max_age: int = 3600,
    force_refresh: bool = False,
) -> tuple[bool, str]:
    """
    Runs a shell command with caching.

    Args:
        cmd: The command to run as a list of strings.
        cache_dir: The directory to store cache files. If None, caching is disabled.
        max_age: Cache validity duration in seconds (default 1 hour).
        force_refresh: If True, ignore existing cache and run the command.

    Returns:
        A tuple (success, output).
    """
    cache_file = None
    cmd_str = " ".join(cmd)

    if cache_dir:
        ensure_dir(cache_dir)
        filename = _generate_cache_filename(cmd)
        cache_file = cache_dir / filename

        if not force_refresh and cache_file.exists():
            mtime = cache_file.stat().st_mtime
            if time.time() - mtime < max_age:
                logging.debug(f"Cache hit for command: {cmd_str}")
                try:
                    with open(cache_file, "r") as f:
                        return True, f.read()
                except OSError as e:
                    logging.warning(f"Failed to read cache file {cache_file}: {e}")

    # Cache miss or stale or forced refresh
    try:
        logging.debug(f"Running {cmd_str}")
        # Capture output. We use universal_newlines=True (text=True in newer python)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )

        output = result.stdout

        if cache_file:
            try:
                with open(cache_file, "w") as f:
                    f.write(output)
            except OSError as e:
                logging.warning(f"Failed to write cache file {cache_file}: {e}")

        return True, output

    except subprocess.CalledProcessError as e:
        logging.debug(f"Command failed: {cmd_str}. Error: {e}")
        # We don't cache failures
        return False, ""
    except FileNotFoundError:
        logging.error(f"Command not found: {cmd[0]}")
        return False, ""
