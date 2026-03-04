import argparse
import logging
import sys
import datetime
from pathlib import Path
from contextlib import redirect_stdout
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .iso_utils import check_command
from .models import (
    MirrorcacheConfig,
    GitConfig,
    ObsConfig,
    GiteaConfig,
    AppConfig,
    BinaryPackage,
    SourcePackage,
    ObsRequest,
    GiteaPullRequest,
)
from .reporting import (
    print_git_report,
    extract_git_hashes,
)
from .reports.iso_packages_report import IsoPackagesReport
from .reports.obs_packages_report import ObsPackagesReport
from .reports.obs_requests_report import ObsRequestsReport
from .reports.gitea_packages_report import GiteaPackagesReport
from .reports.gitea_requests_report import GiteaRequestsReport
from .utils import CACHE_DIR, ensure_dir, REPORT_TIMEZONE
import agama_release_checker.utils as utils


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
    parser.add_argument(
        "-o",
        "--output",
        default="agama-release-status.md",
        help="Specify the output file (default: %(default)s)",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Berlin",
        help="Specify the timezone for timestamps (default: %(default)s)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Verbose logging enabled.")

    try:
        tz = ZoneInfo(args.timezone)
        utils.REPORT_TIMEZONE = tz
    except ZoneInfoNotFoundError:
        logging.error(f"Invalid timezone: {args.timezone}")
        sys.exit(1)
        return

    with open(args.output, "w") as f, redirect_stdout(f):
        logging.info(f"Writing the report to {args.output}")

        print("# Agama Release Status")
        print()
        now = datetime.datetime.now(tz)
        print(
            f"Generated on {now.strftime('%Y-%m-%d %H:%M')} (all times in {args.timezone} time zone)"
        )

        if not all(map(check_command, ["curl", "fuseiso", "fusermount", "git"])):
            logging.error(
                "Required command(s) not found. Please ensure 'curl', 'fuseiso', 'fusermount', and 'git' are installed and in your PATH."
            )
            if not check_command("fuseiso"):
                logging.info("On openSUSE/SLES, try: sudo zypper install fuseiso")
                logging.info("On Debian/Ubuntu, try: sudo apt-get install fuseiso")
            sys.exit(1)
            return

        ensure_dir(CACHE_DIR)
        config: AppConfig = AppConfig.from_file(Path("config.yml"))

        iso_results: list[
            tuple[IsoPackagesReport, str | None, list[BinaryPackage] | None]
        ] = []
        obs_results: list[tuple[ObsPackagesReport, list[SourcePackage] | None]] = []
        gitea_results: list[tuple[GiteaPackagesReport, list[SourcePackage] | None]] = []
        gitea_pr_results: list[tuple[GiteaRequestsReport, list[GiteaPullRequest]]] = []
        obs_requests_results: list[tuple[ObsRequestsReport, list[ObsRequest]]] = []
        all_git_hashes: dict[str, set[str]] = {}
        binary_patterns_by_source: dict[str, list[str]] = (
            config.binary_patterns_by_source
        )

        repos_to_process = [
            r
            for r in config.repositories
            if (args.internal or not r.internal)
            and (not args.repo or r.name in args.repo)
        ]

        if not repos_to_process:
            logging.warning("No repositories to process found.")

        for repo in repos_to_process:
            match repo:
                case MirrorcacheConfig():
                    iso_report = IsoPackagesReport(repo)
                    latest_iso_url, iso_packages = iso_report.run()

                    iso_results.append((iso_report, latest_iso_url, iso_packages))
                    if iso_packages:
                        new_hashes = extract_git_hashes(
                            iso_packages, binary_patterns_by_source
                        )
                        for name, hashes in new_hashes.items():
                            if name not in all_git_hashes:
                                all_git_hashes[name] = set()
                            all_git_hashes[name].update(hashes)

                case ObsConfig():
                    obs_report = ObsPackagesReport(
                        repo,
                        binary_patterns_by_source,
                        config.spec_names_by_package,
                        no_cache=args.no_command_cache,
                    )
                    latest_url, obs_packages = obs_report.run()

                    obs_results.append((obs_report, obs_packages))
                    if obs_packages:
                        new_hashes = extract_git_hashes(
                            obs_packages, binary_patterns_by_source
                        )
                        for name, hashes in new_hashes.items():
                            if name not in all_git_hashes:
                                all_git_hashes[name] = set()
                            all_git_hashes[name].update(hashes)

                    if repo.submit_requests:
                        requests_report = ObsRequestsReport(
                            repo,
                            binary_patterns_by_source,
                            no_cache=args.no_command_cache,
                            recent_requests=args.recent_rq,
                        )
                        _, requests = requests_report.run()
                        if requests:
                            obs_requests_results.append((requests_report, requests))

                case GiteaConfig():
                    gitea_report = GiteaPackagesReport(
                        repo,
                        binary_patterns_by_source,
                        config.spec_names_by_package,
                        no_cache=args.no_command_cache,
                    )
                    _, gitea_packages = gitea_report.run()

                    gitea_results.append((gitea_report, gitea_packages))
                    if gitea_packages:
                        new_hashes = extract_git_hashes(
                            gitea_packages, binary_patterns_by_source
                        )
                        for name, hashes in new_hashes.items():
                            if name not in all_git_hashes:
                                all_git_hashes[name] = set()
                            all_git_hashes[name].update(hashes)

                    gitea_pr_report = GiteaRequestsReport(
                        repo,
                        binary_patterns_by_source,
                        no_cache=args.no_command_cache,
                    )
                    _, prs = gitea_pr_report.run()
                    if prs:
                        gitea_pr_results.append((gitea_pr_report, prs))

                case GitConfig():
                    pass

        for iso_rpt, latest_iso_url, iso_pkgs in iso_results:
            iso_rpt.render(latest_iso_url, iso_pkgs, binary_patterns_by_source)
        for obs_rpt, obs_pkgs in obs_results:
            obs_rpt.render(obs_pkgs)
        for gitea_rpt, gitea_pkgs in gitea_results:
            gitea_rpt.render(gitea_pkgs)
        for pr_rpt, pr_list in gitea_pr_results:
            pr_rpt.render(pr_list)
        for rq_rpt, rq_list in obs_requests_results:
            rq_rpt.render(rq_list)

        print_git_report(all_git_hashes, config.git_configs)

        print()
        print("---")
        print(
            "Report created with [Agama Release Checker](https://github.com/mvidner/agama-release-checker)"
        )


if __name__ == "__main__":
    main()
