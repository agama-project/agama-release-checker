import logging
import re
from collections.abc import Sequence
from urllib.parse import urljoin
import fnmatch

from .models import (
    GitConfig,
    BinaryPackage,
    SourcePackage,
)

Package = BinaryPackage | SourcePackage
from .git_manager import GitManager
from .utils import format_timestamp
from typing import TypeVar

T = TypeVar("T", BinaryPackage, SourcePackage)


def extract_git_hashes(
    packages: Sequence[Package], binary_patterns_by_source: dict[str, list[str]]
) -> dict[str, set[str]]:
    """Extracts git hashes from the version strings of packages, grouped by source rpm."""
    git_hashes: dict[str, set[str]] = {}
    pkg_map = {pkg.name: pkg for pkg in packages}
    for source_rpm, binary_patterns in binary_patterns_by_source.items():
        for pattern in binary_patterns:
            for pkg_name, pkg_details in pkg_map.items():
                if fnmatch.fnmatch(pkg_name, pattern):
                    version = pkg_details.version
                    match = re.search(r"([0-9a-fA-F]{7,})$", version)
                    if match:
                        if source_rpm not in git_hashes:
                            git_hashes[source_rpm] = set()
                        git_hashes[source_rpm].add(match.group(1))
    return git_hashes


def print_markdown_table(headers: list[str], rows: list[list[str]]) -> None:
    """Prints a generic markdown table.

    If a row has more columns than headers, the extra columns are ignored.
    """
    if not headers:
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Print header
    header_str = (
        "| " + " | ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)) + " |"
    )
    print(header_str)

    # Print separator
    sep_str = "|-" + "-|-".join("-" * widths[i] for i in range(len(widths))) + "-|"
    print(sep_str)

    # Print rows
    for row in rows:
        row_str = (
            "| "
            + " | ".join(
                f"{str(cell):<{widths[i]}}"
                for i, cell in enumerate(row)
                if i < len(widths)
            )
            + " |"
        )
        print(row_str)


class LinkManager:
    """Manages markdown reference links for git commits."""

    def __init__(self, git_configs: Sequence[GitConfig]) -> None:
        self.config_map = {cfg.name: cfg for cfg in git_configs}
        self.links: dict[str, str] = {}

    def get_repo_config(self, source_rpm: str) -> GitConfig | None:
        """Determines the GitConfig for a given source RPM name."""
        repo_name = source_rpm
        if repo_name not in self.config_map and "agama" in source_rpm:
            if "agama" in self.config_map:
                repo_name = "agama"
        return self.config_map.get(repo_name)

    def register_hash(self, source_rpm: str, githash: str) -> str | None:
        """Registers a git hash and returns its reference link or None if repo unknown."""
        config = self.get_repo_config(source_rpm)
        if config:
            url = urljoin(config.url, f"commit/{githash}")
            self.links[githash] = url
            return f"[{githash}][]"
        return None

    def format_version(self, source_rpm: str, version: str) -> str:
        """Formats a version string, replacing a trailing git hash with a reference link.

        Example:
            >>> manager = LinkManager([GitConfig(name="agama", url="https://github.com/agama-project/agama/")])
            >>> manager.format_version("agama", "1.0.a6a0f3735")
            '1.0.[a6a0f3735][]'
        """
        match = re.search(r"([0-9a-fA-F]{7,})$", version)
        if match:
            githash = match.group(1)
            ref = self.register_hash(source_rpm, githash)
            if ref:
                return version[: match.start(1)] + ref
        return version

    def print_definitions(self) -> None:
        """Prints the markdown reference definitions at the end of the report."""
        if not self.links:
            return
        print()
        for githash, url in sorted(self.links.items()):
            print(f"[{githash}]: {url}")


def print_git_report(
    git_hashes: dict[str, set[str]],
    git_configs: list[GitConfig],
    link_manager: LinkManager,
) -> None:
    """Prints the git commit report."""
    if not git_hashes:
        return

    if not git_configs:
        logging.warning(
            "No 'git' configuration found in config.yml. Cannot print commit URLs."
        )
        return

    print("\n## Git Commits")

    config_map = {cfg.name: cfg for cfg in git_configs}

    # Organize hashes by repo name, applying fallback logic
    hashes_by_repo: dict[str, set[str]] = {}

    for source_rpm, hashes in git_hashes.items():
        config = link_manager.get_repo_config(source_rpm)
        if config:
            repo_name = config.name
            if repo_name not in hashes_by_repo:
                hashes_by_repo[repo_name] = set()
            hashes_by_repo[repo_name].update(hashes)
        else:
            logging.debug(f"No git config found for package {source_rpm}")

    for repo_name, hashes in sorted(hashes_by_repo.items()):
        git_config = config_map[repo_name]
        print(f"\n### Repo: {repo_name}\n")

        manager = GitManager(git_config.url, git_config.name)
        manager.update_repo()

        rows = []
        for githash in hashes:
            timestamp, description = manager.get_commit_info(githash)
            desc = description or "Unknown"
            ref = link_manager.register_hash(repo_name, githash)
            if ref:
                # If we have a tag or something, the description might have it.
                # The diff showed: | 2026-03-04 12:16 | v19.pre-1865-g[187e0fd7e] | |
                # Let's try to wrap the hash in the description too if it matches.
                if githash in desc:
                    desc = desc.replace(githash, ref)
                else:
                    desc = f"{desc} ({ref})"
            rows.append([format_timestamp(timestamp), desc])

        # Sort by timestamp (column 0), handling "Unknown" to appear last
        rows.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

        headers = ["Timestamp", "Description"]
        print_markdown_table(headers, rows)


def print_packages_table(
    all_found: dict[str, list[T]],
    source_type: str,
    link_manager: LinkManager,
) -> None:
    r"""Prints a simplified table of source packages with their version and release.

    Checks for inconsistencies within each source package group.

    Example:
        all_found = {
            "agama": [
                BinaryPackage(name="agama", version="1.0", release="1", arch="x86_64"),
                BinaryPackage(name="agama-cli", version="1.0", release="1", arch="x86_64"),
            ],
            "agama-web-ui": [
                SourcePackage(name="agama-web-ui", version="1.1", release="1"),
                SourcePackage(name="agama-web-ui", version="1.2", release="1"),
            ]
        }
        print_packages_table(all_found, "ISO", link_manager)

    Output:
        | Source Name  | Version | Release   |
        |--------------|---------|-----------|
        | agama        | 1.0     | 1         |
        | agama-web-ui | 1.1     | 1.../!\   |
    """
    flat = [pkg for pkgs in all_found.values() for pkg in pkgs]
    if not flat:
        print(f"  (No matching packages found in {source_type})")
        return

    headers = ["Source Name", "Version", "Release"]
    rows: list[list[str]] = []
    for source_rpm, found in sorted(all_found.items()):
        if not found:
            continue

        first_pkg = found[0]
        version = link_manager.format_version(source_rpm, first_pkg.version)
        release = first_pkg.release

        # Check for inconsistencies
        inconsistent = False
        for pkg in found[1:]:
            if pkg.version != first_pkg.version or pkg.release != release:
                inconsistent = True
                break

        suffix = ".../!\\" if inconsistent else ""
        rows.append([source_rpm, version, release + suffix])

    print_markdown_table(headers, rows)
