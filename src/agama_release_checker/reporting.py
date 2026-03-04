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
    """Prints a generic markdown table."""
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
            + " | ".join(f"{str(cell):<{widths[i]}}" for i, cell in enumerate(row))
            + " |"
        )
        print(row_str)


def print_git_report(
    git_hashes: dict[str, set[str]],
    git_configs: list[GitConfig],
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
        repo_name = source_rpm

        # Fallback logic: if repo not known but package contains "agama", try "agama" repo
        if repo_name not in config_map and "agama" in source_rpm:
            if "agama" in config_map:
                repo_name = "agama"

        if repo_name in config_map:
            if repo_name not in hashes_by_repo:
                hashes_by_repo[repo_name] = set()
            hashes_by_repo[repo_name].update(hashes)
        else:
            logging.debug(f"No git config found for package {source_rpm}")

    for repo_name, hashes in sorted(hashes_by_repo.items()):
        git_config = config_map[repo_name]
        git_base_url = git_config.url
        print(f"\n### Repo: {repo_name}\n")

        manager = GitManager(git_config.url, git_config.name)
        manager.update_repo()

        rows = []
        for githash in hashes:
            timestamp, description = manager.get_commit_info(githash)
            link = urljoin(git_base_url, f"commit/{githash}")
            rows.append(
                [
                    format_timestamp(timestamp),
                    description or "Unknown",
                    link,
                ]
            )

        # Sort by timestamp (column 0), handling "Unknown" to appear last
        rows.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

        headers = ["Timestamp", "Description", "Link"]
        print_markdown_table(headers, rows)
