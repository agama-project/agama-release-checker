import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any
from .models import Package


def check_command(command: str) -> bool:
    """Checks if a command is available in PATH."""
    return shutil.which(command) is not None


def mount_iso(iso_path: Path, mount_point: Path) -> bool:
    """Mounts an ISO file using fuseiso."""
    logging.debug(f"Mounting ISO {iso_path} to {mount_point}")
    try:
        mount_point.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["fuseiso", str(iso_path), str(mount_point)],
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logging.debug(f"ISO successfully mounted to {mount_point}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Error mounting ISO {iso_path}: {e}")
        return False


def unmount_iso(mount_point: Path) -> bool:
    """Unmounts a fuseiso mounted directory."""
    logging.debug(f"Unmounting {mount_point}")
    try:
        subprocess.run(
            ["fusermount", "-u", str(mount_point)],
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logging.debug(f"Successfully unmounted {mount_point}")
        os.rmdir(mount_point)
        logging.debug(f"Removed mount point directory {mount_point}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Error unmounting {mount_point}: {e}")
        return False


def get_packages_from_metadata_file(packages_json_maybe_gz: Path) -> List[Package]:
    """
    Parses a .packages.json.gz or .packages.json file to get a list of all packages.
    """
    if not packages_json_maybe_gz.exists():
        logging.error(f"Metadata file not found: {packages_json_maybe_gz}")
        return []

    # Try as gzipped file first
    try:
        with gzip.open(packages_json_maybe_gz, "rt", encoding="utf-8") as f:
            data = json.load(f)
            return [Package(**p) for p in data]
    except OSError as e:
        logging.debug(
            f"Failed to parse gzipped metadata file {packages_json_maybe_gz} due to OSError: {e}. Trying plain JSON."
        )
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(
            f"Failed to parse gzipped metadata file {packages_json_maybe_gz}: {e}"
        )
        # If it's a JSON error, it's likely a malformed JSON inside a gzip, not a plain file
        return []

    # If gzipped failed, try as plain file
    try:
        with open(packages_json_maybe_gz, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Package(**p) for p in data]
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(
            f"Failed to parse plain metadata file {packages_json_maybe_gz}: {e}"
        )
        return []

    return []  # Should not reach here if file exists and is valid JSON/GZIP-JSON


def get_packages_from_metadata(mount_point: Path) -> List[Package]:
    """
    Parses LiveOS/.packages.json.gz or LiveOS/.packages.json to get a list of all packages.
    """
    metadata_path_gz = mount_point / "LiveOS" / ".packages.json.gz"
    metadata_path_plain = mount_point / "LiveOS" / ".packages.json"

    logging.debug(
        f"Reading packages from {metadata_path_gz} or {metadata_path_plain}..."
    )

    if metadata_path_gz.exists():
        return get_packages_from_metadata_file(metadata_path_gz)
    elif metadata_path_plain.exists():
        return get_packages_from_metadata_file(metadata_path_plain)

    logging.error(
        f"Neither gzipped nor plain metadata file found at {mount_point / 'LiveOS'}."
    )
    return []
