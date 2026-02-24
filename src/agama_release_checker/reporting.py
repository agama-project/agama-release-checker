import logging
import re
from typing import List, Dict, Any, Set, Optional, Tuple
from urllib.parse import urljoin
import fnmatch

from .models import GitConfig, Package, ObsRequest, GiteaPullRequest
from .git_manager import GitManager


def extract_git_hashes(
    packages: List[Package], rpm_map: Dict[str, List[str]]
) -> Dict[str, Set[str]]:
    """Extracts git hashes from the version strings of packages, grouped by source rpm."""
    git_hashes: Dict[str, Set[str]] = {}
    pkg_map = {pkg.name: pkg for pkg in packages}
    for source_rpm, binary_patterns in rpm_map.items():
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


def print_markdown_table(headers: List[str], rows: List[List[str]]) -> None:
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


def print_packages_table(
    rpm_map: Dict[str, List[str]], packages: List[Package], label: str = "ISO"
) -> None:
    """Prints a formatted table of packages."""

    pkg_map = {pkg.name: pkg for pkg in packages}
    all_found_packages_by_source = {}

    for source_rpm, binary_patterns in rpm_map.items():
        found_packages = []
        for pattern in binary_patterns:
            for pkg_name, pkg_details in pkg_map.items():
                if fnmatch.fnmatch(pkg_name, pattern):
                    found_packages.append(pkg_details)

        all_found_packages_by_source[source_rpm] = sorted(
            found_packages, key=lambda p: p.name
        )

    all_packages_flat = [
        pkg for pkgs in all_found_packages_by_source.values() for pkg in pkgs
    ]
    if not all_packages_flat:
        print(f"  (No matching packages found in {label})")
        return

    headers = ["Source Name", "Name", "Version", "Release"]
    rows = []
    for source_rpm, found_packages in sorted(all_found_packages_by_source.items()):
        rows.append([source_rpm, "", "", ""])
        for pkg in found_packages:
            rows.append(["", pkg.name, pkg.version, pkg.release])

    print_markdown_table(headers, rows)


def print_obs_packages_table(
    rpm_map_keys: List[str],
    specs_map: Dict[str, List[str]],
    packages: List[Package],
) -> None:
    """Prints a formatted table of OBS source packages."""
    pkg_map = {pkg.name: pkg for pkg in packages}
    all_found_packages_by_source = {}

    for obs_package in rpm_map_keys:
        found_packages = []
        # Get expected source names (specs) for this OBS package
        source_names = specs_map.get(obs_package, [obs_package])

        for source_name in source_names:
            if source_name in pkg_map:
                found_packages.append(pkg_map[source_name])

        all_found_packages_by_source[obs_package] = sorted(
            found_packages, key=lambda p: p.name
        )

    all_packages_flat = [
        pkg for pkgs in all_found_packages_by_source.values() for pkg in pkgs
    ]
    if not all_packages_flat:
        print(f"  (No matching packages found in OBS)")
        return

    headers = ["Source Name", "Name", "Version", "Release"]
    rows = []
    for source_rpm, found_packages in sorted(all_found_packages_by_source.items()):
        rows.append([source_rpm, "", "", ""])
        for pkg in found_packages:
            rows.append(["", pkg.name, pkg.version, pkg.release])

    print_markdown_table(headers, rows)


def print_iso_results(
    results: List[Tuple[Dict[str, Any], Optional[str], Optional[List[Package]]]],
    rpm_map: Dict[str, List[str]],
) -> None:
    """Prints results for ISO images."""
    for mirrorcache_config, latest_iso_url, iso_packages in results:
        print(f"\n## ISO: {mirrorcache_config['name']}\n")
        if latest_iso_url:
            print(f"URL: {latest_iso_url}\n")
        if iso_packages:
            print_packages_table(rpm_map, iso_packages, label="ISO")
        else:
            print("  (No packages found)")


def print_obs_results(
    results: List[Tuple[Dict[str, Any], Optional[List[Package]]]],
    rpm_map_keys: List[str],
    specs_map: Dict[str, List[str]],
) -> None:
    """Prints results for OBS projects."""
    for obs_config, packages in results:
        print(f"\n## OBS: {obs_config['name']}\n")
        print(f"Project: {obs_config['url']}\n")
        if packages:
            print_obs_packages_table(rpm_map_keys, specs_map, packages)
        else:
            print("  (No packages found)")


def print_gitea_results(
    results: List[Tuple[Dict[str, Any], Optional[List[Package]]]],
    rpm_map_keys: List[str],
    specs_map: Dict[str, List[str]],
) -> None:
    """Prints results for Gitea projects."""
    for gitea_config, packages in results:
        print(f"\n## Gitea: {gitea_config['name']}\n")
        print(f"URL: {gitea_config['url']}\n")
        if packages:
            print_obs_packages_table(rpm_map_keys, specs_map, packages)
        else:
            print("  (No packages found)")


def print_gitea_pull_requests_results(
    results: List[Tuple[Dict[str, Any], List[GiteaPullRequest]]],
) -> None:
    """Prints results for Gitea pull requests."""
    for gitea_config, prs in results:
        print(f"\n## Gitea Pull Requests: {gitea_config.get('name', 'Unknown')}\n")
        print(f"URL: {gitea_config.get('url', 'Unknown')}\n")

        if not prs:
            print("  (No matching pull requests found)")
            continue

        headers = [
            "Updated",
            "Index",
            "State",
            "Mergeable",
            "Title",
            "Author",
            "Comments",
        ]
        rows = []
        for pr in prs:
            rows.append(
                [
                    pr.updated_at,
                    f"[{pr.index}]({pr.url})",
                    pr.state,
                    "Yes" if pr.mergeable else "No",
                    pr.title,
                    pr.author,
                    pr.comments,
                ]
            )

        # Sort by Updated (column 0)
        rows.sort(key=lambda x: x[0])

        print_markdown_table(headers, rows)


def print_obs_requests_results(
    results: List[Tuple[Dict[str, Any], List[ObsRequest]]],
) -> None:
    """Prints results for OBS submit requests."""
    for obs_config, requests in results:
        print(f"\n## OBS Submit Requests: {obs_config.get('name', 'Unknown')}\n")
        print(f"Project: {obs_config.get('url', 'Unknown')}\n")

        if not requests:
            print("  (No pending requests found)")
            continue

        headers = ["Updated", "Created", "ID", "State", "Source", "Target"]
        rows = []
        for req in requests:
            source = f"{req.source_project}/{req.source_package}"
            target = f"{req.target_project}/{req.target_package}"
            rows.append(
                [
                    req.updated_at,
                    req.created_at,
                    req.id,
                    req.state,
                    source,
                    target,
                ]
            )

        # Sort by Updated (column 0)
        rows.sort(key=lambda x: x[0])

        print_markdown_table(headers, rows)


def print_git_report(
    git_hashes: Dict[str, Set[str]],
    git_configs: List[GitConfig],
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
    hashes_by_repo: Dict[str, Set[str]] = {}

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
                    timestamp or "Unknown",
                    description or "Unknown",
                    link,
                ]
            )

        # Sort by timestamp (column 0), handling "Unknown" to appear last
        rows.sort(key=lambda x: x[0] if x[0] != "Unknown" else "9999-12-31")

        headers = ["Timestamp", "Description", "Link"]
        print_markdown_table(headers, rows)
