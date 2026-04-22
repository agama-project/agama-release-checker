import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .models import BinaryPackage


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


class IsoMounter:
    """Context manager for mounting and unmounting an ISO file."""

    def __init__(self, iso_path: Path, mount_point: Path):
        self.iso_path = iso_path
        self.mount_point = mount_point
        self.mounted = False

    def __enter__(self) -> Path:
        if mount_iso(self.iso_path, self.mount_point):
            self.mounted = True
            return self.mount_point
        raise RuntimeError(f"Failed to mount ISO: {self.iso_path}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.mounted:
            unmount_iso(self.mount_point)
            # unmount_iso already tries to rmdir, but we might want to ensure it is gone
            if self.mount_point.exists():
                try:
                    self.mount_point.rmdir()
                except OSError:
                    pass


def is_wwwdirfs_available() -> bool:
    """Checks if the wwwdirfs command is available."""
    return check_command("wwwdirfs")


def mount_www(url: str, mount_point: Path) -> bool:
    """Mounts a remote HTTP directory listing using wwwdirfs."""
    logging.debug(f"Mounting WWW directory {url} to {mount_point}")
    try:
        mount_point.mkdir(parents=True, exist_ok=True)
        # Use ?jsontable as required by the example if it's openSUSE download
        url_with_query = url if "?" in url else f"{url}?jsontable"
        subprocess.run(
            ["wwwdirfs", url_with_query, str(mount_point)],
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logging.debug(f"WWW directory successfully mounted to {mount_point}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Error mounting WWW directory {url}: {e}")
        return False


def unmount_www(mount_point: Path) -> bool:
    """Unmounts a wwwdirfs mounted directory."""
    return unmount_iso(mount_point)  # same fusermount command


class WWWMounter:
    """Context manager for mounting and unmounting a remote HTTP directory."""

    def __init__(self, url: str, mount_point: Path):
        self.url = url
        self.mount_point = mount_point
        self.mounted = False

    def __enter__(self) -> Path:
        if mount_www(self.url, self.mount_point):
            self.mounted = True
            return self.mount_point
        raise RuntimeError(f"Failed to mount WWW directory: {self.url}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.mounted:
            unmount_www(self.mount_point)
            if self.mount_point.exists():
                try:
                    self.mount_point.rmdir()
                except OSError:
                    pass


def get_packages_from_metadata_file(
    packages_json_maybe_gz: Path,
) -> list[BinaryPackage]:
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
            return [BinaryPackage(**p) for p in data]
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
            return [BinaryPackage(**p) for p in data]
    except (json.JSONDecodeError, KeyError) as e:
        logging.error(
            f"Failed to parse plain metadata file {packages_json_maybe_gz}: {e}"
        )
        return []

    return []  # Should not reach here if file exists and is valid JSON/GZIP-JSON


def get_metadata_path(mount_point: Path) -> Path | None:
    """
    Returns the path to LiveOS/.packages.json.gz or LiveOS/.packages.json if they exist.
    """
    metadata_path_gz = mount_point / "LiveOS" / ".packages.json.gz"
    if metadata_path_gz.exists():
        return metadata_path_gz

    metadata_path_plain = mount_point / "LiveOS" / ".packages.json"
    if metadata_path_plain.exists():
        return metadata_path_plain

    return None


def get_packages_from_metadata(mount_point: Path) -> list[BinaryPackage]:
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
