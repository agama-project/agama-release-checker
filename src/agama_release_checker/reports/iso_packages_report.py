import logging
import os
from collections.abc import Sequence

import fnmatch
from pathlib import Path

from agama_release_checker.iso_utils import (
    mount_iso,
    unmount_iso,
    get_packages_from_metadata,
)
from agama_release_checker.models import MirrorcacheConfig, BinaryPackage
from agama_release_checker.network import find_iso_urls, download_file
from agama_release_checker.reporting import print_markdown_table
from agama_release_checker.utils import CACHE_DIR, ensure_dir


class IsoPackagesReport:
    def __init__(self, config: MirrorcacheConfig):
        self.config = config

    def _cleanup_old_isos(self, repo_dir: Path, keep: int = 3) -> None:
        """Keeps only the 'keep' newest ISO files in the repository directory."""
        if not repo_dir.exists():
            return

        files = [
            f for f in repo_dir.iterdir() if f.is_file() and f.name.endswith(".iso")
        ]
        if len(files) <= keep:
            return

        # Sort by modification time (newest first)
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Identify files to delete
        files_to_delete = files[keep:]
        for f in files_to_delete:
            try:
                logging.info(f"Removing old ISO: {f.name}")
                f.unlink()
            except OSError as e:
                logging.warning(f"Failed to remove old ISO {f.name}: {e}")

    def run(self) -> tuple[str | None, list[BinaryPackage] | None]:
        """Processes a single mirrorcache configuration."""
        logging.info(f"Processing mirrorcache: {self.config.name}")
        base_url = self.config.url
        patterns = self.config.files

        # Directory structure: CACHE_DIR/repo_type/repo_name/
        repo_dir = CACHE_DIR / "mirrorcache" / self.config.name
        ensure_dir(repo_dir)

        iso_urls = find_iso_urls(base_url, patterns, cache_file=repo_dir / "index.html")

        if not iso_urls:
            logging.warning(f"No ISOs found matching patterns {patterns} at {base_url}")
            return None, None

        iso_urls.sort()
        latest_iso_url = iso_urls[-1]
        logging.debug(f"Determined latest ISO: {latest_iso_url}")

        iso_filename = latest_iso_url.split("/")[-1]
        iso_filepath = repo_dir / iso_filename

        if not iso_filepath.exists():
            if not download_file(latest_iso_url, iso_filepath):
                return latest_iso_url, None  # Skip if download fails
        else:
            logging.info(f"In cache: {iso_filename}")
            # Touch the file to update mtime, ensuring it's treated as recent
            try:
                iso_filepath.touch()
            except OSError:
                pass

        # Cleanup old ISOs
        self._cleanup_old_isos(repo_dir)

        mount_point = CACHE_DIR / "mounts" / self.config.name
        ensure_dir(mount_point)

        if mount_iso(iso_filepath, mount_point):
            try:
                iso_packages = get_packages_from_metadata(mount_point)
                return latest_iso_url, iso_packages
            finally:
                unmount_iso(mount_point)
                try:
                    mount_point.rmdir()
                except OSError:
                    pass
        return latest_iso_url, None

    def _print_packages_table(
        self,
        binary_patterns_by_source: dict[str, list[str]],
        packages: Sequence[BinaryPackage],
    ) -> None:
        """Prints a formatted table of binary packages grouped by source."""
        pkg_map = {pkg.name: pkg for pkg in packages}
        all_found: dict[str, list[BinaryPackage]] = {}

        for source_rpm, binary_patterns in binary_patterns_by_source.items():
            found = []
            for pattern in binary_patterns:
                for pkg_name, pkg_details in pkg_map.items():
                    if fnmatch.fnmatch(pkg_name, pattern):
                        found.append(pkg_details)
            all_found[source_rpm] = sorted(found, key=lambda p: p.name)

        flat = [pkg for pkgs in all_found.values() for pkg in pkgs]
        if not flat:
            print("  (No matching packages found in ISO)")
            return

        headers = ["Source Name", "Name", "Version", "Release"]
        rows: list[list[str]] = []
        for source_rpm, found in sorted(all_found.items()):
            rows.append([source_rpm, "", "", ""])
            for pkg in found:
                rows.append(["", pkg.name, pkg.version, pkg.release])
        print_markdown_table(headers, rows)

    def render(
        self,
        latest_iso_url: str | None,
        packages: list[BinaryPackage] | None,
        binary_patterns_by_source: dict[str, list[str]],
    ) -> None:
        """Renders the ISO packages report as markdown."""
        print(f"\n## ISO: {self.config.name}\n")
        if latest_iso_url:
            print(f"URL: {latest_iso_url}\n")
        if packages:
            self._print_packages_table(binary_patterns_by_source, packages)
        else:
            print("  (No packages found)")
