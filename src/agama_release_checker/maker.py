import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agama_release_checker.models import (
        MakerConfig,
        GiteaSubmitStrategy,
        PackageSubmissionConfig,
    )
else:
    from .models import MakerConfig


class ReleaseMaker:
    """Handles submitting packages to OBS and Gitea.

    This class provides methods to automate the submission of multiple
    packages between OBS projects or from OBS to Gitea repositories,
    including synchronization and PR creation.
    """

    def __init__(self, config: "MakerConfig"):
        """Initializes the ReleaseMaker with the given configuration."""
        self.config = config

    def _run_command(
        self, cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        """Runs a command and returns the completed process.

        Captures and logs stdout and stderr on failure for easier debugging.
        """
        logging.info(f"Running command: {' '.join(cmd)} in {cwd or '.'}")
        try:
            return subprocess.run(
                cmd, check=True, capture_output=True, text=True, cwd=cwd
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {' '.join(cmd)}")
            if e.stdout:
                logging.error(f"STDOUT: {e.stdout.strip()}")
            if e.stderr:
                logging.error(f"STDERR: {e.stderr.strip()}")
            raise

    def submit_to_obs(self) -> None:
        """Submit all configured packages from source to target OBS project."""
        source_project = self.config.obs_submissions.source_project
        target_project = self.config.obs_submissions.target_project

        for pkg in self.config.package_submissions.keys():
            logging.info(f"Submitting {pkg} from {source_project} to {target_project}")
            cmd = [
                "osc",
                "sr",
                "--yes",
                "-m",
                f"Automatic update from {source_project}",
                source_project,
                pkg,
                target_project,
            ]
            try:
                self._run_command(cmd)
            except subprocess.CalledProcessError as e:
                if "The request contains no actions" in e.stderr:
                    logging.warning(f"No changes to submit for {pkg}")
                else:
                    logging.error(f"Failed to submit {pkg}: {e.stderr.strip()}")
                    raise

    def _get_gitea_info(self, url: str) -> tuple[str, str, str]:
        """Parses a Gitea URL (SSH or HTTPS) and returns (host, owner, repo)."""
        from urllib.parse import urlparse

        if url.startswith("gitea@"):
            # Format: gitea@host:owner/repo.git
            rest = url.removeprefix("gitea@")
            host, path = rest.split(":", 1)
            path = path.removesuffix(".git")
            owner, repo = path.split("/", 1)
            return host, owner, repo
        else:
            # Format: https://host/owner/repo[.git]
            parsed = urlparse(url)
            host = parsed.netloc
            path = parsed.path.strip("/").removesuffix(".git")
            owner, repo = path.split("/", 1)
            return host, owner, repo

    def _submit_to_gitea_custom(
        self,
        pkg: str,
        strategy: "GiteaSubmitStrategy",
    ) -> None:
        """Submit a package to Gitea using a custom strategy."""
        source_project = self.config.gitea_submissions.source_project
        target_branch = (
            strategy.target_branch or self.config.gitea_submissions.target_branch
        )
        fork_org = strategy.fork_org or self.config.gitea_submissions.fork_org

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # 1. Clone source repo
            source_repo_dir = tmp_path / f"{pkg}-source"
            logging.info(f"Cloning source repo {strategy.source_repo}")
            self._run_command(
                ["git", "clone", strategy.source_repo, str(source_repo_dir)]
            )

            # 2. Run build command
            logging.info(f"Running build command: {strategy.source_run}")
            self._run_command(strategy.source_run.split(), cwd=source_repo_dir)

            # 3. Clone target repo
            target_repo_dir = tmp_path / f"{pkg}-target"
            logging.info(
                f"Cloning target repo {strategy.target_repo} (branch {target_branch})"
            )
            self._run_command(
                [
                    "git",
                    "clone",
                    "--branch",
                    target_branch,
                    strategy.target_repo,
                    str(target_repo_dir),
                ]
            )

            # 4. Handle Fork
            host, target_owner, repo_name = self._get_gitea_info(strategy.target_repo)
            push_remote = "origin"
            push_owner = target_owner

            if fork_org and fork_org != target_owner:
                fork_url = f"gitea@{host}:{fork_org}/{repo_name}.git"
                logging.info(f"Adding fork remote: {fork_url}")
                self._run_command(
                    ["git", "remote", "add", "fork", fork_url], cwd=target_repo_dir
                )
                push_remote = "fork"
                push_owner = fork_org

            # 5. Create branch
            branch_name = f"{target_branch}-update-{pkg}"
            logging.info(f"Creating branch {branch_name}")
            self._run_command(
                ["git", "checkout", "-b", branch_name], cwd=target_repo_dir
            )

            # 6. Sync files
            source_dist_dir = source_repo_dir / strategy.source_dir
            target_dist_dir = target_repo_dir / strategy.target_dir

            logging.info(f"Syncing files from {source_dist_dir} to {target_dist_dir}")
            if target_dist_dir.exists():
                shutil.rmtree(target_dist_dir)
            shutil.copytree(source_dist_dir, target_dist_dir)

            # 7. Commit and push
            self._run_command(["git", "add", "."], cwd=target_repo_dir)
            res = self._run_command(
                ["git", "status", "--porcelain"], cwd=target_repo_dir
            )
            if not res.stdout.strip():
                logging.info("No changes to commit")
                return

            # Extract the diff of any .changes files to use in the PR description.
            # Note: '*.changes' here matches recursively in subdirectories as well.
            diff_res = self._run_command(
                ["git", "diff", "--cached", "--", "*.changes"], cwd=target_repo_dir
            )
            changes_diff = diff_res.stdout.strip()
            pr_description = f"Automatic update of {pkg} from {source_project}"
            if changes_diff:
                pr_description += f"\n\n```diff\n{changes_diff}\n```"

            self._run_command(
                ["git", "commit", "-m", f"Update {pkg} from {source_project}"],
                cwd=target_repo_dir,
            )
            self._run_command(
                ["git", "push", push_remote, branch_name, "--force"],
                cwd=target_repo_dir,
            )

            # 8. Create PR using tea
            repo_path = f"{target_owner}/{repo_name}"
            # For tea, head is <owner>:<branch> if it's from a fork
            head_spec = f"{push_owner}:{branch_name}"

            logging.info(f"Creating PR for {pkg} in {repo_path}")
            check_pr_cmd = [
                "tea",
                "pr",
                "list",
                "--repo",
                repo_path,
                "--state",
                "open",
                "-f",
                "index,title,state,author,milestone,updated,labels,head,base,url",
                "--output",
                "json",
            ]

            try:
                res = self._run_command(check_pr_cmd)
                all_prs = json.loads(res.stdout)
                existing_prs = [
                    pr
                    for pr in all_prs
                    if pr.get("head") in (branch_name, head_spec)
                    and pr.get("base") == target_branch
                ]
                if existing_prs:
                    logging.info(
                        f"Pull request already exists for {pkg}: {existing_prs[0].get('url')}"
                    )
                else:
                    pr_cmd = [
                        "tea",
                        "pr",
                        "create",
                        "--repo",
                        repo_path,
                        "--base",
                        target_branch,
                        "--head",
                        head_spec,
                        "--title",
                        f"Update {pkg} from {source_project}",
                        "--description",
                        pr_description,
                    ]
                    try:
                        self._run_command(pr_cmd)
                    except subprocess.CalledProcessError as e:
                        if "pull request already exists" in e.stderr:
                            logging.info(f"Pull request already exists for {pkg}")
                        else:
                            raise
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                logging.error(f"Failed to check or create PR for {pkg}: {e}")
                raise

    def submit_to_gitea(
        self,
        obs_api: str = "https://api.suse.de",
        gitea_host: str = "src.suse.de",
    ) -> None:
        """Submit all configured packages from source OBS to Gitea.

        Checks out source from OBS (defaulting to IBS), clones the target Gitea repo,
        syncs files, and creates or updates a pull request.
        """
        source_project = self.config.gitea_submissions.source_project
        target_org = self.config.gitea_submissions.target_org
        default_target_branch = self.config.gitea_submissions.target_branch
        fork_org = self.config.gitea_submissions.fork_org

        for pkg, pkg_cfg in self.config.package_submissions.items():
            if pkg_cfg.gitea_submit:
                self._submit_to_gitea_custom(
                    pkg,
                    pkg_cfg.gitea_submit,
                )
                continue

            target_branch = default_target_branch

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # 1. Checkout from OBS
                logging.info(f"Checking out {pkg} from OBS {source_project}")
                co_cmd = ["osc"]
                if obs_api:
                    co_cmd.extend(["-A", obs_api])
                co_cmd.extend(["co", source_project, pkg])
                self._run_command(co_cmd, cwd=tmp_path)
                obs_pkg_dir = tmp_path / source_project / pkg

                # 2. Clone from Gitea
                gitea_remote = f"gitea@{gitea_host}:{target_org}/{pkg}.git"
                git_repo_dir = tmp_path / f"{pkg}-git"
                logging.info(
                    f"Cloning {pkg} from Gitea {gitea_remote} (branch {target_branch})"
                )
                self._run_command(
                    [
                        "git",
                        "clone",
                        "--branch",
                        target_branch,
                        gitea_remote,
                        str(git_repo_dir),
                    ]
                )

                # 3. Handle Fork
                push_remote = "origin"
                push_owner = target_org
                if fork_org and fork_org != target_org:
                    fork_url = f"gitea@{gitea_host}:{fork_org}/{pkg}.git"
                    logging.info(f"Adding fork remote: {fork_url}")
                    self._run_command(
                        ["git", "remote", "add", "fork", fork_url], cwd=git_repo_dir
                    )
                    push_remote = "fork"
                    push_owner = fork_org

                # 4. Create branch
                branch_name = f"{target_branch}-update"
                logging.info(f"Creating branch {branch_name}")
                self._run_command(
                    ["git", "checkout", "-b", branch_name], cwd=git_repo_dir
                )

                # 5. Sync files (excluding .git and .gitattributes)
                logging.info("Syncing files from OBS to Gitea")
                # Remove all files in git repo except .git and .gitattributes
                for item in git_repo_dir.iterdir():
                    if item.name in (".git", ".gitattributes"):
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

                # 6. Commit and push
                self._run_command(["git", "add", "."], cwd=git_repo_dir)
                # Check if there are changes
                res = self._run_command(
                    ["git", "status", "--porcelain"], cwd=git_repo_dir
                )
                if not res.stdout.strip():
                    logging.info("No changes to commit")
                    continue

                # Extract the diff of any .changes files to use in the PR description.
                # Note: '*.changes' here matches recursively in subdirectories as well.
                diff_res = self._run_command(
                    ["git", "diff", "--cached", "--", "*.changes"], cwd=git_repo_dir
                )
                changes_diff = diff_res.stdout.strip()
                pr_description = f"Automatic update from {source_project}"
                if changes_diff:
                    pr_description += f"\n\n```diff\n{changes_diff}\n```"

                self._run_command(
                    ["git", "commit", "-m", f"Update from OBS {source_project}"],
                    cwd=git_repo_dir,
                )
                self._run_command(
                    ["git", "push", push_remote, branch_name, "--force"],
                    cwd=git_repo_dir,
                )

                # 7. Create PR using tea
                repo_path = f"{target_org}/{pkg}"
                # For tea, head is <owner>:<branch> if it's from a fork
                head_spec = f"{push_owner}:{branch_name}"

                logging.info(f"Creating PR for {pkg} in {repo_path}")
                # Check for existing PR first
                check_pr_cmd = [
                    "tea",
                    "pr",
                    "list",
                    "--repo",
                    repo_path,
                    "--state",
                    "open",
                    "-f",
                    "index,title,state,author,milestone,updated,labels,head,base,url",
                    "--output",
                    "json",
                ]

                try:
                    res = self._run_command(check_pr_cmd)
                    all_prs = json.loads(res.stdout)
                    # Filter manually as tea doesn't support head/base filtering
                    existing_prs = [
                        pr
                        for pr in all_prs
                        if pr.get("head") in (branch_name, head_spec)
                        and pr.get("base") == target_branch
                    ]
                    if existing_prs:
                        logging.info(
                            f"Pull request already exists for {pkg}: {existing_prs[0].get('url')}"
                        )
                    else:
                        pr_cmd = [
                            "tea",
                            "pr",
                            "create",
                            "--repo",
                            repo_path,
                            "--base",
                            target_branch,
                            "--head",
                            head_spec,
                            "--title",
                            f"Update from OBS {source_project}",
                            "--description",
                            pr_description,
                        ]
                        try:
                            self._run_command(pr_cmd)
                        except subprocess.CalledProcessError as e:
                            if "pull request already exists" in e.stderr:
                                logging.info(f"Pull request already exists for {pkg}")
                            else:
                                raise
                except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                    logging.error(f"Failed to check or create PR for {pkg}: {e}")
                    raise


def main() -> None:
    """Main entry point for the agama-release-maker script."""
    parser = argparse.ArgumentParser(
        description="Automates package submissions for Agama releases."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="maker-config-testing.yml",
        help="Configuration file (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("obs-submit", help="Submit packages to OBS.")

    subparsers.add_parser("gitea-submit", help="Submit packages to Gitea.")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    config = MakerConfig.from_file(Path(args.config))
    maker = ReleaseMaker(config)

    try:
        if args.command == "obs-submit":
            maker.submit_to_obs()
        elif args.command == "gitea-submit":
            maker.submit_to_gitea()
    except Exception as e:
        logging.error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
