import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agama_release_checker.models import AppConfig
else:
    from .models import AppConfig


class ReleaseMaker:
    """Handles submitting packages to OBS and Gitea."""

    def __init__(self, config: "AppConfig"):
        self.config = config

    def _run_command(
        self, cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        """Runs a command and returns the completed process."""
        logging.info(f"Running command: {' '.join(cmd)} in {cwd or '.'}")
        return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=cwd)

    def submit_to_obs(self, source_project: str, target_project: str):
        """Submit all configured packages from source to target OBS project."""
        for pkg in self.config.obs_packages:
            logging.info(f"Submitting {pkg} from {source_project} to {target_project}")
            cmd = ["osc", "sr", source_project, pkg, target_project]
            try:
                self._run_command(cmd)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to submit {pkg}: {e.stderr.strip()}")
                raise

    def submit_to_gitea(self, source_project: str, target_org: str, target_branch: str):
        """Submit all configured packages from source OBS to Gitea."""
        for pkg in self.config.obs_packages:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # 1. Checkout from OBS
                logging.info(f"Checking out {pkg} from OBS {source_project}")
                self._run_command(["osc", "co", source_project, pkg], cwd=tmp_path)
                obs_pkg_dir = tmp_path / source_project / pkg

                # 2. Clone from Gitea
                # Use a generic URL or try to determine it.
                # Assuming gitea@src.opensuse.org:ORG/REPO.git
                gitea_remote = f"gitea@src.opensuse.org:{target_org}/{pkg}.git"
                git_repo_dir = tmp_path / f"{pkg}-git"
                logging.info(f"Cloning {pkg} from Gitea {gitea_remote}")
                self._run_command(["git", "clone", gitea_remote, str(git_repo_dir)])

                # 3. Create a branch for the update
                branch_name = f"{target_branch}-update"
                logging.info(f"Creating branch {branch_name}")
                self._run_command(
                    ["git", "checkout", "-b", branch_name], cwd=git_repo_dir
                )

                # 4. Sync files (excluding .git)
                logging.info("Syncing files from OBS to Gitea")
                # Remove all files in git repo except .git
                for item in git_repo_dir.iterdir():
                    if item.name == ".git":
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

                # Copy from OBS to Gitea
                for item in obs_pkg_dir.iterdir():
                    if item.name == ".osc":
                        continue
                    if item.is_dir():
                        shutil.copytree(item, git_repo_dir / item.name)
                    else:
                        shutil.copy2(item, git_repo_dir / item.name)

                # 5. Commit and push
                self._run_command(["git", "add", "."], cwd=git_repo_dir)
                # Check if there are changes
                res = self._run_command(
                    ["git", "status", "--porcelain"], cwd=git_repo_dir
                )
                if not res.stdout.strip():
                    logging.info("No changes to commit")
                    continue

                self._run_command(
                    ["git", "commit", "-m", f"Update from OBS {source_project}"],
                    cwd=git_repo_dir,
                )
                self._run_command(
                    ["git", "push", "origin", branch_name, "--force"], cwd=git_repo_dir
                )

                # 6. Create PR using tea
                logging.info(f"Creating PR for {pkg} in {target_org}/{pkg}")
                pr_cmd = [
                    "tea",
                    "pr",
                    "create",
                    "--repo",
                    f"{target_org}/{pkg}",
                    "--base",
                    target_branch,
                    "--head",
                    branch_name,
                    "--title",
                    f"Update from OBS {source_project}",
                    "--description",
                    f"Automatic update from {source_project}",
                ]
                self._run_command(pr_cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Automates package submissions for Agama releases."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yml",
        help="Configuration file (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    obs_parser = subparsers.add_parser("obs-submit", help="Submit packages to OBS.")
    obs_parser.add_argument("source", help="Source project name.")
    obs_parser.add_argument("target", help="Target project name.")

    gitea_parser = subparsers.add_parser(
        "gitea-submit", help="Submit packages to Gitea."
    )
    gitea_parser.add_argument("source", help="Source OBS project name.")
    gitea_parser.add_argument("org", help="Target Gitea organization.")
    gitea_parser.add_argument("branch", help="Target branch.")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    config = AppConfig.from_file(Path(args.config))
    maker = ReleaseMaker(config)

    try:
        if args.command == "obs-submit":
            maker.submit_to_obs(args.source, args.target)
        elif args.command == "gitea-submit":
            maker.submit_to_gitea(args.source, args.org, args.branch)
    except Exception as e:
        logging.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
