import logging
import os
from collections.abc import Sequence

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agama_release_checker.reporting import LinkManager

from agama_release_checker.iso_utils import (
    mount_iso,
    unmount_iso,
    get_packages_from_metadata,
    get_metadata_path,
    get_packages_from_metadata_file,
)
from agama_release_checker.models import MirrorcacheConfig, BinaryPackage
from agama_release_checker.network import find_iso_urls, download_file
from agama_release_checker.reporting import print_markdown_table, print_packages_table
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
                # Also remove cached metadata files if they exist
                for ext in [".packages.json", ".packages.json.gz"]:
                    meta_cache = f.with_suffix(ext)
                    if meta_cache.exists():
                        logging.info(f"Removing cached metadata: {meta_cache.name}")
                        meta_cache.unlink()
            except OSError as e:
                logging.warning(f"Failed to remove old ISO or metadata {f.name}: {e}")

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

        # Caching logic for metadata
        # We check if we already have the metadata cached
        # Look for both .gz and plain json
        metadata_cache_gz = iso_filepath.with_suffix(".packages.json.gz")
        metadata_cache_plain = iso_filepath.with_suffix(".packages.json")

        if metadata_cache_gz.exists():
            logging.info(f"Using cached metadata: {metadata_cache_gz.name}")
            return latest_iso_url, get_packages_from_metadata_file(metadata_cache_gz)
        if metadata_cache_plain.exists():
            logging.info(f"Using cached metadata: {metadata_cache_plain.name}")
            return latest_iso_url, get_packages_from_metadata_file(metadata_cache_plain)

        # Not in cache, we need to mount and extract
        mount_point = CACHE_DIR / "mounts" / self.config.name
        ensure_dir(mount_point)

        if mount_iso(iso_filepath, mount_point):
            try:
                metadata_path = get_metadata_path(mount_point)
                if metadata_path:
                    # Cache the metadata file
                    dest_path = iso_filepath.with_suffix(metadata_path.suffix)
                    logging.info(f"Caching metadata from ISO to {dest_path.name}")
                    import shutil

                    shutil.copy2(metadata_path, dest_path)
                    return latest_iso_url, get_packages_from_metadata_file(dest_path)
                else:
                    logging.error(f"No metadata found in mounted ISO: {iso_filename}")
                    return latest_iso_url, None
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
        link_manager: "LinkManager",
    ) -> None:
        """Prints a simplified table of source packages with their version and release."""
        pkg_map = {pkg.name: pkg for pkg in packages}
        all_found: dict[str, list[BinaryPackage]] = {}

        for source_rpm, binary_patterns in binary_patterns_by_source.items():
            found = []
            for pattern in binary_patterns:
                for pkg_name, pkg_details in pkg_map.items():
                    if fnmatch.fnmatch(pkg_name, pattern):
                        found.append(pkg_details)
            # Sort by name to be deterministic for "picking the first one"
            all_found[source_rpm] = sorted(found, key=lambda p: p.name)

        print_packages_table(all_found, "ISO", link_manager=link_manager)

    def render(
        self,
        latest_iso_url: str | None,
        packages: list[BinaryPackage] | None,
        binary_patterns_by_source: dict[str, list[str]],
        link_manager: "LinkManager",
    ) -> None:
        """Renders the ISO packages report as markdown."""
        print(f"\n## ISO: {self.config.name}\n")
        if latest_iso_url:
            print(f"URL: {latest_iso_url}\n")
        if packages:
            self._print_packages_table(
                binary_patterns_by_source, packages, link_manager=link_manager
            )
        else:
            print("  (No packages found)")
