import argparse
import logging
import sys
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from .config import load_config
from .iso_utils import check_command
from .models import (
    MirrorcacheConfig,
    ObsConfig,
    GiteaConfig,
    AppConfig,
    BinaryPackage,
    SourcePackage,
    ObsRequest,
    GiteaPullRequest,
)
from .reporting import (
    print_iso_results,
    print_obs_results,
    print_gitea_results,
    print_gitea_pull_requests_results,
    print_git_report,
    print_obs_requests_results,
    extract_git_hashes,
)
from .reports.iso_report import RpmsOnIsoReport
from .reports.obs_report import PackagesInObsReport
from .reports.obs_requests import ObsSubmitRequestsReport
from .reports.gitea_report import PackagesInGiteaReport
from .reports.gitea_pull_requests import GiteaPullRequestsReport
from .utils import CACHE_DIR, ensure_dir


def main() -> None:
    # Configure logging
    log = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    parser = argparse.ArgumentParser(
        description="Checks for the latest Agama release, downloads it, and verifies package versions."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )
    parser.add_argument(
        "-r",
        "--repo",
        action="append",
        help="Specify the name of the repository to process. Can be used multiple times.",
    )
    parser.add_argument(
        "--no-command-cache",
        action="store_true",
        help="Force refresh of cached command results (e.g. osc commands).",
    )
    parser.add_argument(
        "--recent-rq",
        action="store_true",
        help="Show requests of all states modified within the past two weeks.",
    )
    parser.add_argument(
        "-i",
        "--internal",
        action="store_true",
        help="Enable processing of internal resources (reachable only by VPN).",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    print("# Agama Release Status")
    print()
    print(
        f"Generated on {datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}"
    )

    if not all(map(check_command, ["curl", "fuseiso", "fusermount", "git"])):
        logging.error(
            "Required command(s) not found. Please ensure 'curl', 'fuseiso', 'fusermount', and 'git' are installed and in your PATH."
        )
        if not check_command("fuseiso"):
            logging.info("On openSUSE/SLES, try: sudo zypper install fuseiso")
            logging.info("On Debian/Ubuntu, try: sudo apt-get install fuseiso")
        sys.exit(1)

    ensure_dir(CACHE_DIR)
    config: AppConfig = load_config(Path("config.yml"))

    iso_results: List[
        Tuple[Dict[str, Any], Optional[str], Optional[List[BinaryPackage]]]
    ] = []
    obs_results: List[Tuple[Dict[str, Any], Optional[List[SourcePackage]]]] = []
    gitea_results: List[Tuple[Dict[str, Any], Optional[List[SourcePackage]]]] = []
    gitea_pr_results: List[Tuple[Dict[str, Any], List[GiteaPullRequest]]] = []
    obs_requests_results: List[Tuple[Dict[str, Any], List[ObsRequest]]] = []
    all_git_hashes: Dict[str, Set[str]] = {}
    binary_patterns_by_source: Dict[str, List[str]] = config.binary_patterns_by_source

    repos_to_process = [
        r
        for r in config.repositories
        if (args.internal or not r.get("internal", False))
        and (not args.repo or r.get("name") in args.repo)
    ]

    if not repos_to_process:
        logging.warning("No repositories to process found.")

    for repo in repos_to_process:
        repo_type = repo.get("type")
        if repo_type == "mirrorcache":
            mc_args = {
                k: repo[k] for k in ["type", "name", "url", "files"] if k in repo
            }
            mirrorcache_config = MirrorcacheConfig(**mc_args)

            iso_report = RpmsOnIsoReport(mirrorcache_config)
            latest_iso_url, iso_packages = iso_report.run()

            iso_results.append(
                (
                    {
                        "name": mirrorcache_config.name,
                        "url": mirrorcache_config.url,
                        "files": mirrorcache_config.files,
                    },
                    latest_iso_url,
                    iso_packages,
                )
            )
            if iso_packages:
                new_hashes = extract_git_hashes(iso_packages, binary_patterns_by_source)
                for name, hashes in new_hashes.items():
                    if name not in all_git_hashes:
                        all_git_hashes[name] = set()
                    all_git_hashes[name].update(hashes)

        elif repo_type == "obs":
            obs_config = ObsConfig(**repo)
            obs_report = PackagesInObsReport(
                obs_config,
                binary_patterns_by_source,
                config.spec_names_by_package,
                no_cache=args.no_command_cache,
            )
            latest_url, obs_packages = obs_report.run()

            obs_results.append(
                (
                    {"name": obs_config.name, "url": obs_config.url},
                    obs_packages,
                )
            )
            if obs_packages:
                new_hashes = extract_git_hashes(obs_packages, binary_patterns_by_source)
                for name, hashes in new_hashes.items():
                    if name not in all_git_hashes:
                        all_git_hashes[name] = set()
                    all_git_hashes[name].update(hashes)

            if obs_config.submit_requests:
                requests_report = ObsSubmitRequestsReport(
                    obs_config,
                    binary_patterns_by_source,
                    no_cache=args.no_command_cache,
                    recent_requests=args.recent_rq,
                )
                _, requests = requests_report.run()
                if requests:
                    obs_requests_results.append(
                        (
                            {"name": obs_config.name, "url": obs_config.url},
                            requests,
                        )
                    )

        elif repo_type == "gitea":
            gitea_config = GiteaConfig(**repo)
            gitea_report = PackagesInGiteaReport(
                gitea_config,
                binary_patterns_by_source,
                config.spec_names_by_package,
                no_cache=args.no_command_cache,
            )
            _, gitea_packages = gitea_report.run()

            gitea_results.append(
                (
                    {"name": gitea_config.name, "url": gitea_config.url},
                    gitea_packages,
                )
            )
            if gitea_packages:
                new_hashes = extract_git_hashes(
                    gitea_packages, binary_patterns_by_source
                )
                for name, hashes in new_hashes.items():
                    if name not in all_git_hashes:
                        all_git_hashes[name] = set()
                    all_git_hashes[name].update(hashes)

            gitea_pr_report = GiteaPullRequestsReport(
                gitea_config,
                binary_patterns_by_source,
                no_cache=args.no_command_cache,
            )
            _, prs = gitea_pr_report.run()
            if prs:
                gitea_pr_results.append(
                    (
                        {"name": gitea_config.name, "url": gitea_config.url},
                        prs,
                    )
                )

        elif repo_type == "git":
            pass

    if iso_results:
        print_iso_results(iso_results, binary_patterns_by_source)
    if obs_results:
        print_obs_results(
            obs_results,
            list(binary_patterns_by_source.keys()),
            config.spec_names_by_package,
        )
    if gitea_results:
        print_gitea_results(
            gitea_results,
            list(binary_patterns_by_source.keys()),
            config.spec_names_by_package,
        )
    if gitea_pr_results:
        print_gitea_pull_requests_results(gitea_pr_results)
    if obs_requests_results:
        print_obs_requests_results(obs_requests_results)

    print_git_report(all_git_hashes, config.git_configs)


if __name__ == "__main__":
    main()
