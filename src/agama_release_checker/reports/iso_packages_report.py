import logging
import os
import shutil
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
    IsoMounter,
    WWWMounter,
    is_wwwdirfs_available,
)
from agama_release_checker.models import (
    MirrorcacheConfig,
    BinaryPackage,
    GitTimestamp,
    GitRevisionTimestamps,
)
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

        # Directory structure: CACHE_DIR/repo_type/repo_name/
        repo_dir = CACHE_DIR / "mirrorcache" / self.config.name
        ensure_dir(repo_dir)

        latest_iso_url = self._find_latest_iso_url(repo_dir)
        if not latest_iso_url:
            return None, None

        iso_filename = latest_iso_url.split("/")[-1]
        iso_filepath = repo_dir / iso_filename

        # Cleanup old ISOs
        self._cleanup_old_isos(repo_dir)

        packages = self._get_cached_metadata(iso_filepath)
        if packages is not None:
            return latest_iso_url, packages

        # Try extracting without downloading using wwwdirfs
        if is_wwwdirfs_available():
            packages = self._extract_metadata_via_wwwdirfs(latest_iso_url, iso_filepath)
            if packages is not None:
                return latest_iso_url, packages
            logging.info("Falling back to downloading ISO")

        # Fallback: Download and extract
        local_iso_filepath = self._ensure_iso_local(latest_iso_url, repo_dir)
        if not local_iso_filepath:
            return latest_iso_url, None

        packages = self._extract_and_cache_metadata(local_iso_filepath)
        return latest_iso_url, packages

    def _extract_metadata_via_wwwdirfs(
        self, latest_iso_url: str, cache_filepath: Path
    ) -> list[BinaryPackage] | None:
        """Mounts the remote directory containing the ISO, mounts the ISO from it, and extracts metadata."""
        url_dir = latest_iso_url.rsplit("/", 1)[0]
        iso_filename = latest_iso_url.split("/")[-1]

        mount_point_www = CACHE_DIR / "mounts_www" / self.config.name
        ensure_dir(mount_point_www)

        try:
            with WWWMounter(url_dir, mount_point_www) as mounted_www:
                iso_in_www = mounted_www / iso_filename
                if not iso_in_www.exists():
                    logging.warning(
                        f"ISO file not found in wwwdirfs mount: {iso_in_www}"
                    )
                    return None

                # Now mount the ISO from the www mount point
                mount_point_iso = CACHE_DIR / "mounts" / self.config.name
                ensure_dir(mount_point_iso)
                try:
                    with IsoMounter(iso_in_www, mount_point_iso) as mounted_iso:
                        metadata_path = get_metadata_path(mounted_iso)
                        if metadata_path:
                            cache_suffix = (
                                ".packages.json.gz"
                                if metadata_path.name.endswith(".packages.json.gz")
                                else ".packages.json"
                            )
                            dest_path = cache_filepath.with_suffix(cache_suffix)
                            logging.info(
                                f"Caching metadata from WWW/ISO to {dest_path.name}"
                            )

                            if dest_path.exists():
                                dest_path.unlink()
                            shutil.copy(metadata_path, dest_path)
                            return get_packages_from_metadata_file(dest_path)
                        else:
                            logging.warning(
                                f"No metadata found in mounted WWW/ISO: {iso_filename}"
                            )
                            # Cache an empty list to prevent fallback and future mounting
                            dest_path = cache_filepath.with_suffix(".packages.json")
                            with open(dest_path, "w") as f:
                                f.write("[]")
                            return []
                except RuntimeError as e:
                    logging.warning(
                        f"Could not extract metadata via WWW/ISO {iso_filename}: {e}"
                    )
                    return None
        except RuntimeError as e:
            logging.warning(f"Could not mount WWW directory {url_dir}: {e}")
            return None

    def _find_latest_iso_url(self, repo_dir: Path) -> str | None:
        """Finds the latest ISO URL based on configuration patterns."""
        base_url = self.config.url
        patterns = self.config.files
        iso_urls = find_iso_urls(base_url, patterns, cache_file=repo_dir / "index.html")

        if not iso_urls:
            logging.warning(f"No ISOs found matching patterns {patterns} at {base_url}")
            return None

        iso_urls.sort()
        latest_iso_url = iso_urls[-1]
        logging.debug(f"Determined latest ISO: {latest_iso_url}")
        return latest_iso_url

    def _ensure_iso_local(self, latest_iso_url: str, repo_dir: Path) -> Path | None:
        """Ensures the latest ISO is available locally, downloading if necessary."""
        iso_filename = latest_iso_url.split("/")[-1]
        iso_filepath = repo_dir / iso_filename

        if not iso_filepath.exists():
            if not download_file(latest_iso_url, iso_filepath):
                return None  # Skip if download fails
        else:
            logging.info(f"In cache: {iso_filepath}")
            # Touch the file to update mtime, ensuring it's treated as recent
            try:
                iso_filepath.touch()
            except OSError:
                pass
        return iso_filepath

    def _get_cached_metadata(self, iso_filepath: Path) -> list[BinaryPackage] | None:
        """Checks if metadata for the given ISO is already cached."""
        # Look for both .gz and plain json
        metadata_cache_gz = iso_filepath.with_suffix(".packages.json.gz")
        metadata_cache_plain = iso_filepath.with_suffix(".packages.json")

        if metadata_cache_gz.exists():
            logging.info(f"In cache: {metadata_cache_gz}")
            return get_packages_from_metadata_file(metadata_cache_gz)
        if metadata_cache_plain.exists():
            logging.info(f"In cache: {metadata_cache_plain}")
            return get_packages_from_metadata_file(metadata_cache_plain)
        return None

    def _extract_and_cache_metadata(
        self, iso_filepath: Path
    ) -> list[BinaryPackage] | None:
        """Mounts the ISO, extracts metadata, and caches it."""
        mount_point = CACHE_DIR / "mounts" / self.config.name
        ensure_dir(mount_point)

        try:
            with IsoMounter(iso_filepath, mount_point) as mounted_path:
                metadata_path = get_metadata_path(mounted_path)
                if metadata_path:
                    # Cache the metadata file, using the same suffix
                    # convention as the cache lookup above
                    cache_suffix = (
                        ".packages.json.gz"
                        if metadata_path.name.endswith(".packages.json.gz")
                        else ".packages.json"
                    )
                    dest_path = iso_filepath.with_suffix(cache_suffix)
                    logging.info(f"Caching metadata from ISO to {dest_path.name}")

                    # Remove existing file first — copy2 preserves the
                    # ISO's read-only permissions, so a stale copy would
                    # block overwriting.
                    if dest_path.exists():
                        dest_path.unlink()
                    shutil.copy(metadata_path, dest_path)
                    return get_packages_from_metadata_file(dest_path)
                else:
                    logging.warning(
                        f"No metadata found in mounted ISO: {iso_filepath.name}"
                    )
                    # Cache an empty list to prevent future mounting
                    dest_path = iso_filepath.with_suffix(".packages.json")
                    with open(dest_path, "w") as f:
                        f.write("[]")
                    return []
        except RuntimeError as e:
            logging.error(f"Could not extract metadata from {iso_filepath.name}: {e}")
            return None

    def _print_packages_table(
        self,
        binary_patterns_by_source: dict[str, list[str]],
        packages: Sequence[BinaryPackage],
        link_manager: "LinkManager",
        timestamps: GitRevisionTimestamps | None = None,
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

        print_packages_table(
            all_found, "ISO", link_manager=link_manager, timestamps=timestamps
        )

    def render(
        self,
        latest_iso_url: str | None,
        packages: list[BinaryPackage] | None,
        binary_patterns_by_source: dict[str, list[str]],
        link_manager: "LinkManager",
        timestamps: GitRevisionTimestamps | None = None,
    ) -> None:
        """Renders the ISO packages report as markdown."""
        print(f"\n## ISO: {self.config.name}\n")
        if latest_iso_url:
            print(f"URL: {latest_iso_url}\n")
        if packages:
            self._print_packages_table(
                binary_patterns_by_source,
                packages,
                link_manager=link_manager,
                timestamps=timestamps,
            )
        else:
            print("  (No packages found)")
