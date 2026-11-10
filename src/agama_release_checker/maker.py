import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import json
import re
import shlex
from collections.abc import Callable
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
from .upstream import ObsUpdater, UpstreamRelease

RELEASE_PROJECT = "systemsmanagement:Agama:Release"
IBS_API = "https://api.suse.de"

# command -> package providing it
REQUIRED_TOOLS = {
    "osc": "osc",
    "git": "git",
    "tea": "gitea-tea",
    "filterdiff": "patchutils",
}


def format_cmd(cmd: list[str], max_arg: int = 60) -> str:
    """Formats a command for logging, shortening long or multi-line arguments.

    >>> format_cmd(["tea", "pr", "create", "--description", "a\\nb"])
    'tea pr create --description a...'
    """

    def short(arg: str) -> str:
        first = arg.splitlines()[0] if arg else arg
        if len(first) > max_arg or first != arg:
            return first[:max_arg] + "..."
        return arg

    return shlex.join(short(a) for a in cmd)


def check_tools(tools: list[str]) -> None:
    """Fails with an installation hint if some of the commands are missing."""
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        packages = " ".join(REQUIRED_TOOLS.get(t, t) for t in missing)
        raise RuntimeError(
            f"Missing commands: {', '.join(missing)}. "
            f"Install them with: sudo zypper install {packages}"
        )


class ReleaseMaker:
    """Handles submitting packages to OBS and Gitea.

    This class provides methods to automate the submission of multiple
    packages between OBS projects or from OBS to Gitea repositories,
    including synchronization and PR creation.
    """

    def __init__(self, config: "MakerConfig"):
        """Initializes the ReleaseMaker with the given configuration."""
        self.config = config
        # host -> tea login (name, user, ...)
        self._tea_logins: dict[str, dict[str, str]] = {}
        # (package, outcome, details) of the submissions, for the summary
        self.results: list[tuple[str, str, str]] = []

    def _record(self, pkg: str, outcome: str, details: str = "") -> None:
        """Records the outcome of submitting a package."""
        self.results.append((pkg, outcome, details))

    def print_summary(self) -> None:
        """Prints the outcome of every submission."""
        if not self.results:
            return
        width = max(len(pkg) for pkg, _, _ in self.results)
        print("\nSummary:")
        for pkg, outcome, details in self.results:
            print(f"  {pkg:<{width}}  {outcome:<14} {details}".rstrip())

    def _tea_login(self, host: str) -> list[str]:
        """Returns the `tea` arguments selecting the login for a Gitea host.

        Without them tea uses its default login, which may be another server
        (e.g. src.opensuse.org instead of src.suse.de).
        """
        return ["--login", self._find_tea_login(host)["name"]]

    def _tea_user(self, host: str) -> str:
        """Returns the user of the tea login for a Gitea host."""
        return self._find_tea_login(host)["user"]

    def _find_tea_login(self, host: str) -> dict[str, str]:
        """Returns the tea login whose URL is on the host."""
        if host not in self._tea_logins:
            from urllib.parse import urlparse

            res = self._run_command(["tea", "logins", "list", "--output", "json"])
            for login in json.loads(res.stdout or "[]"):
                if urlparse(login.get("url", "")).hostname == host:
                    self._tea_logins[host] = login
                    break
            else:
                raise RuntimeError(
                    f"No tea login for {host}, add one with: "
                    f"tea logins add --url https://{host} --name IBS --user USERNAME --oauth"
                )
        return self._tea_logins[host]

    def _resolve_fork_org(self, configured: str | None, target_repo_url: str) -> str:
        """Returns the configured fork org or else the user of the tea login."""
        if configured:
            return configured
        host, _, _ = self._get_gitea_info(target_repo_url)
        return self._tea_user(host)

    def _run_command(
        self, cmd: list[str], cwd: Path | None = None, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Runs a command and returns the completed process.

        Captures and logs stdout and stderr on failure for easier debugging.
        """
        logging.info(f"Running command: {format_cmd(cmd)} in {cwd or '.'}")
        logging.debug(f"Full command: {cmd}")
        try:
            return subprocess.run(
                cmd, check=True, capture_output=True, text=True, cwd=cwd, input=input
            )
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {format_cmd(cmd)}")
            if e.stdout:
                logging.error(f"STDOUT: {e.stdout.strip()}")
            if e.stderr:
                logging.error(f"STDERR: {e.stderr.strip()}")
            raise

    def _get_obs_changes_diff(
        self, source_project: str, pkg: str, target_project: str
    ) -> str:
        """Returns the diff of .changes files between source and target."""
        try:
            diff_res = self._run_command(
                ["osc", "sr", "--diff", source_project, pkg, target_project]
            )
            if not diff_res.stdout:
                return ""

            # Filter the diff to only include .changes files
            filter_cmd = ["filterdiff", "-i", "*.changes"]
            res = self._run_command(filter_cmd, input=diff_res.stdout)
            return res.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            # FileNotFoundError happens if filterdiff is missing.
            # CalledProcessError might happen if osc sr --diff fails (e.g. no changes)
            logging.debug(f"Failed to get changes diff for {pkg}: {e}")
            return ""

    def submit_to_obs(self, packages: list[str]) -> None:
        """Submit all configured packages from source to target OBS project."""
        if not self.config.obs_submissions:
            raise RuntimeError("No obs_submissions in the configuration")
        source_project = self.config.obs_submissions.source_project
        target_project = self.config.obs_submissions.target_project

        if not packages:
            packages = list(self.config.package_submissions.keys())

        for pkg in packages:
            logging.info(f"Submitting {pkg} from {source_project} to {target_project}")

            message = f"Automatic update from {source_project}"
            changes_diff = self._get_obs_changes_diff(
                source_project, pkg, target_project
            )
            if changes_diff:
                message += f"\n\n{changes_diff}"

            cmd = [
                "osc",
                "sr",
                "--yes",
                "-m",
                message,
                source_project,
                pkg,
                target_project,
            ]
            try:
                res = self._run_command(cmd)
            except subprocess.CalledProcessError as e:
                if "The request contains no actions" in e.stderr:
                    logging.warning(f"No changes to submit for {pkg}")
                    self._record(pkg, "no changes")
                    continue
                logging.error(f"Failed to submit {pkg}: {e.stderr.strip()}")
                self._record(pkg, "failed", (e.stderr.strip().splitlines() or [""])[-1])
                raise
            match = re.search(r"request id (\d+)", res.stdout or "")
            self._record(pkg, "submitted", f"request {match.group(1)}" if match else "")

    def build_check_projects(self) -> list[tuple[str | None, str]]:
        """Returns the (API, project) pairs whose builds should be checked.

        These are the OBS project updated from Git and the IBS project the
        Gitea submissions are taken from.
        """
        projects: list[tuple[str | None, str]] = []
        if self.config.obs_update:
            projects.append((None, self.config.obs_update.project))
        elif self.config.obs_submissions:
            projects.append((None, self.config.obs_submissions.source_project))
        projects.append((IBS_API, self.config.gitea_submissions.source_project))
        return projects

    def check_builds(self) -> bool:
        """Reports failed builds in the configured projects; True if none failed."""
        ok = True
        for api, project in self.build_check_projects():
            cmd = ["osc"] + (["-A", api] if api else [])
            res = self._run_command(cmd + ["results", "--failed", project])
            if res.stdout.strip():
                ok = False
                logging.error(f"Failed builds in {project}:\n{res.stdout.strip()}")
            else:
                logging.info(f"No failed builds in {project}")
        return ok

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

    def _commit_and_get_pr_description(
        self, repo_dir: Path, commit_msg: str, base_pr_desc: str
    ) -> str | None:
        """Stages changes, checks for diffs, commits, and builds a PR description.

        Returns None if there are no changes to commit.
        """
        self._run_command(["git", "add", "."], cwd=repo_dir)
        res = self._run_command(["git", "status", "--porcelain"], cwd=repo_dir)
        if not res.stdout.strip():
            logging.info("No changes to commit")
            return None

        # Extract the diff of any .changes files to use in the PR description.
        # Note: '*.changes' here matches recursively in subdirectories as well.
        diff_res = self._run_command(
            ["git", "diff", "--cached", "--", "*.changes"], cwd=repo_dir
        )
        changes_diff = diff_res.stdout.strip()
        pr_description = base_pr_desc
        if changes_diff:
            pr_description += f"\n\n```diff\n{changes_diff}\n```"

        self._run_command(["git", "commit", "-m", commit_msg], cwd=repo_dir)
        return pr_description

    def _gitea_pr_exists(
        self,
        *,
        pkg: str,
        target_repo_url: str,
        target_branch: str,
        fork_org: str | None,
        branch_name: str,
    ) -> str | None:
        """Returns the URL of an open pull request of the package on Gitea, if any.

        Parses the repository URL to find owner and repo name, then uses the `tea` CLI
        to check if a pull request is already open for the target branch and branch name.
        """
        host, target_owner, repo_name = self._get_gitea_info(target_repo_url)
        push_owner = target_owner
        if fork_org and fork_org != target_owner:
            push_owner = fork_org

        repo_path = f"{target_owner}/{repo_name}"
        head_spec = f"{push_owner}:{branch_name}"

        check_pr_cmd = [
            "tea",
            "pr",
            "list",
            *self._tea_login(host),
            "--repo",
            repo_path,
            "--state",
            "open",
            "-f",
            "index,title,state,author,milestone,updated,labels,head,base,url",
            "--output",
            "json",
        ]

        res = self._run_command(check_pr_cmd)
        all_prs = json.loads(res.stdout)
        existing_prs = [
            pr
            for pr in all_prs
            if pr.get("head") in (branch_name, head_spec)
            and pr.get("base") == target_branch
        ]
        if existing_prs:
            url = str(existing_prs[0].get("url", ""))
            logging.info(f"Pull request already exists for {pkg}: {url}")
            return url or "(open PR)"

        return None

    def _submit_to_gitea_repo(
        self,
        *,
        pkg: str,
        target_repo_url: str,
        target_branch: str,
        fork_org: str | None,
        branch_name: str,
        sync_func: Callable[[Path], None],
        commit_msg: str,
        pr_title: str,
        pr_desc_base: str,
        tmp_path: Path,
    ) -> None:
        """Clones a target Gitea repo, runs a sync callback, commits, pushes, and creates/updates a Gitea PR."""
        # 1. Clone target repo
        target_repo_dir = tmp_path / f"{pkg}-target"
        logging.info(f"Cloning target repo {target_repo_url} (branch {target_branch})")
        self._run_command(
            [
                "git",
                "clone",
                "--branch",
                target_branch,
                target_repo_url,
                str(target_repo_dir),
            ]
        )

        # 2. Handle Fork remote
        host, target_owner, repo_name = self._get_gitea_info(target_repo_url)
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

        # 3. Create branch
        logging.info(f"Creating branch {branch_name}")
        self._run_command(["git", "checkout", "-b", branch_name], cwd=target_repo_dir)

        # 4. Sync files via callback
        sync_func(target_repo_dir)

        # 5. Commit and push
        pr_description = self._commit_and_get_pr_description(
            target_repo_dir,
            commit_msg,
            pr_desc_base,
        )
        if not pr_description:
            self._record(pkg, "no changes")
            return

        self._run_command(
            ["git", "config", "lfs.allowincompletepush", "true"],
            cwd=target_repo_dir,
        )
        self._run_command(
            ["git", "push", push_remote, branch_name, "--force"],
            cwd=target_repo_dir,
        )

        # 6. Create PR using tea
        repo_path = f"{target_owner}/{repo_name}"
        head_spec = f"{push_owner}:{branch_name}"

        logging.info(f"Creating PR for {pkg} in {repo_path}")
        pr_cmd = [
            "tea",
            "pr",
            "create",
            *self._tea_login(host),
            "--repo",
            repo_path,
            "--base",
            target_branch,
            "--head",
            head_spec,
            "--title",
            pr_title,
            "--description",
            pr_description,
        ]
        try:
            res = self._run_command(pr_cmd)
        except subprocess.CalledProcessError as e:
            if "pull request already exists" in e.stderr:
                logging.info(f"Pull request already exists for {pkg}")
                self._record(pkg, "PR exists", f"https://{host}/{repo_path}/pulls")
                return
            logging.error(f"Failed to create PR for {pkg}: {e.stderr.strip()}")
            raise
        match = re.search(r"https?://\S+/pulls/\d+", res.stdout or "")
        self._record(
            pkg,
            "PR created",
            match.group(0) if match else f"https://{host}/{repo_path}/pulls",
        )

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
        fork_org = self._resolve_fork_org(
            strategy.fork_org or self.config.gitea_submissions.fork_org,
            strategy.target_repo,
        )
        branch_name = f"{target_branch}-update-{pkg}"

        try:
            url = self._gitea_pr_exists(
                pkg=pkg,
                target_repo_url=strategy.target_repo,
                target_branch=target_branch,
                fork_org=fork_org,
                branch_name=branch_name,
            )
            if url:
                self._record(pkg, "PR exists", url)
                return
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logging.error(f"Failed to check PR for {pkg}: {e}")
            raise

        temp_obj = tempfile.TemporaryDirectory(
            prefix="agama-release-maker-", delete=False
        )
        with temp_obj as tmpdir:
            tmp_path = Path(tmpdir)

            # 1. Clone source repo (a branch or a tag, if specified)
            source_repo_dir = tmp_path / f"{pkg}-source"
            logging.info(f"Cloning source repo {strategy.source_repo}")
            clone_cmd = ["git", "clone"]
            if strategy.source_branch:
                clone_cmd.extend(["--branch", strategy.source_branch])
            clone_cmd.extend([strategy.source_repo, str(source_repo_dir)])
            self._run_command(clone_cmd)

            # 2. Run build command
            logging.info(f"Running build command: {strategy.source_run}")
            self._run_command(strategy.source_run.split(), cwd=source_repo_dir)

            # 3. Synchronize using our custom logic
            def sync_files(target_repo_dir: Path) -> None:
                source_dist_dir = source_repo_dir / strategy.source_dir
                target_dist_dir = target_repo_dir / strategy.target_dir

                logging.info(
                    f"Syncing files from {source_dist_dir} to {target_dist_dir}"
                )
                if target_dist_dir.exists():
                    shutil.rmtree(target_dist_dir)
                shutil.copytree(source_dist_dir, target_dist_dir)

            self._submit_to_gitea_repo(
                pkg=pkg,
                target_repo_url=strategy.target_repo,
                target_branch=target_branch,
                fork_org=fork_org,
                branch_name=branch_name,
                sync_func=sync_files,
                commit_msg=f"Update {pkg} from {source_project}",
                pr_title=f"Update {pkg} from {source_project}",
                pr_desc_base=f"Automatic update of {pkg} from {source_project}",
                tmp_path=tmp_path,
            )

        # This will not run if a command fails, enabling us to debug the problem
        temp_obj.cleanup()

    def _missing_forks(self, repos: list[tuple[str, str | None]]) -> list[str]:
        """Returns the target repos (as URLs) lacking a fork of the fork_org.

        `repos` are (target repo URL, fork org) pairs.
        """
        missing = []
        for url, fork_org in repos:
            host, owner, repo = self._get_gitea_info(url)
            if not fork_org or fork_org == owner:
                continue
            res = self._run_command(
                ["tea", "api", *self._tea_login(host), f"/repos/{fork_org}/{repo}"]
            )
            data = json.loads(res.stdout or "{}")
            parent = (data.get("parent") or {}).get("full_name")
            if parent != f"{owner}/{repo}":
                missing.append(f"https://{host}/{owner}/{repo}")
        return missing

    def submit_to_gitea(
        self,
        packages: list[str],
        obs_api: str = "https://api.suse.de",
        gitea_host: str = "src.suse.de",
    ) -> None:
        """Submit all configured packages from source OBS to Gitea.

        Checks out source from OBS (defaulting to IBS), clones the target Gitea repo,
        syncs files, and creates or updates a pull request.
        """
        check_tools(["osc", "git", "tea", "filterdiff"])
        source_project = self.config.gitea_submissions.source_project
        target_org = self.config.gitea_submissions.target_org
        default_target_branch = self.config.gitea_submissions.target_branch
        configured_fork_org = self.config.gitea_submissions.fork_org
        fork_org = self._resolve_fork_org(
            configured_fork_org, f"gitea@{gitea_host}:{target_org}/repo.git"
        )

        if not packages:
            packages = list(self.config.package_submissions.keys())

        # Check the forks first, not to fail after submitting some packages
        repos: list[tuple[str, str | None]] = []
        for pkg in packages:
            strategy = self.config.package_submissions[pkg].gitea_submit
            if strategy:
                repos.append(
                    (
                        strategy.target_repo,
                        self._resolve_fork_org(
                            strategy.fork_org or configured_fork_org,
                            strategy.target_repo,
                        ),
                    )
                )
            else:
                repos.append((f"gitea@{gitea_host}:{target_org}/{pkg}.git", fork_org))
        missing = self._missing_forks(repos)
        if missing:
            raise RuntimeError(
                f"{fork_org} has no fork of: {', '.join(missing)}. Fork them "
                "in the web UI or with: tea repos fork --login LOGIN --repo OWNER/REPO"
            )

        current = ""
        try:
            for pkg in packages:
                current = pkg
                self._submit_package_to_gitea(
                    pkg,
                    fork_org,
                    source_project,
                    target_org,
                    default_target_branch,
                    obs_api,
                    gitea_host,
                )
        except Exception as e:
            self._record(current, "failed", str(e).splitlines()[0] if str(e) else "")
            raise

    def _submit_package_to_gitea(
        self,
        pkg: str,
        fork_org: str | None,
        source_project: str,
        target_org: str,
        default_target_branch: str,
        obs_api: str,
        gitea_host: str,
    ) -> None:
        """Submits one package to Gitea (see submit_to_gitea)."""
        pkg_cfg = self.config.package_submissions[pkg]

        if pkg_cfg.gitea_submit:
            self._submit_to_gitea_custom(
                pkg,
                pkg_cfg.gitea_submit,
            )
            return

        target_branch = default_target_branch
        gitea_remote = f"gitea@{gitea_host}:{target_org}/{pkg}.git"
        branch_name = f"{target_branch}-update"

        try:
            url = self._gitea_pr_exists(
                pkg=pkg,
                target_repo_url=gitea_remote,
                target_branch=target_branch,
                fork_org=fork_org,
                branch_name=branch_name,
            )
            if url:
                self._record(pkg, "PR exists", url)
                return
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logging.error(f"Failed to check PR for {pkg}: {e}")
            raise

        temp_obj = tempfile.TemporaryDirectory(
            prefix="agama-release-maker-", delete=False
        )
        with temp_obj as tmpdir:
            tmp_path = Path(tmpdir)

            # 1. Checkout from OBS
            logging.info(f"Checking out {pkg} from OBS {source_project}")
            co_cmd = ["osc"]
            if obs_api:
                co_cmd.extend(["-A", obs_api])
            co_cmd.extend(["co", source_project, pkg])
            self._run_command(co_cmd, cwd=tmp_path)
            obs_pkg_dir = tmp_path / source_project / pkg

            # 2. Synchronize standard OBS files into the cloned repository
            def sync_files(target_repo_dir: Path) -> None:
                logging.info("Syncing files from OBS to Gitea")
                for item in target_repo_dir.iterdir():
                    if item.name in (
                        ".git",
                        ".gitattributes",
                        ".gitignore",
                    ):
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

                for item in obs_pkg_dir.iterdir():
                    if item.name == ".osc":
                        continue
                    if item.is_dir():
                        shutil.copytree(item, target_repo_dir / item.name)
                    else:
                        shutil.copy2(item, target_repo_dir / item.name)

            self._submit_to_gitea_repo(
                pkg=pkg,
                target_repo_url=gitea_remote,
                target_branch=target_branch,
                fork_org=fork_org,
                branch_name=branch_name,
                sync_func=sync_files,
                commit_msg=f"Update from OBS {source_project}",
                pr_title=f"Update from OBS {source_project}",
                pr_desc_base=f"Automatic update from {source_project}",
                tmp_path=tmp_path,
            )

        # This will not run if a command fails, enabling us to debug the problem
        temp_obj.cleanup()


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
    parser.add_argument(
        "--fork-org",
        help="Your Gitea user, overrides fork_org of the configuration",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_obs = subparsers.add_parser("obs-submit", help="Submit packages to OBS.")
    parser_obs.add_argument("packages", nargs="*", help="Limit to these packages only")

    parser_gitea = subparsers.add_parser(
        "gitea-submit", help="Submit packages to Gitea."
    )
    parser_gitea.add_argument(
        "packages", nargs="*", help="Limit to these packages only"
    )

    push_help = "Really push/submit; without it only a dry run is done."

    parser_bump = subparsers.add_parser(
        "bump-version", help="Create the upstream release PR for a version."
    )
    parser_bump.add_argument("version", help="The new version, e.g. 25")
    parser_bump.add_argument("--push", action="store_true", help=push_help)

    parser_tag = subparsers.add_parser(
        "tag-release", help="Tag the merged upstream release PR."
    )
    parser_tag.add_argument("version", help="The released version, e.g. 25")
    parser_tag.add_argument("--push", action="store_true", help=push_help)
    parser_tag.add_argument(
        "--force", action="store_true", help="Tag even if CI did not pass."
    )

    parser_publish = subparsers.add_parser(
        "publish-release",
        help=f"Commit the tagged version to {RELEASE_PROJECT} via the GitHub workflows.",
    )
    parser_publish.add_argument("version", help="The released version, e.g. 25")
    parser_publish.add_argument(
        "--ref",
        help="Git ref to build (default: the vVERSION tag; 'master' is the manual way)",
    )
    parser_publish.add_argument("--push", action="store_true", help=push_help)

    parser_update = subparsers.add_parser(
        "obs-update",
        help="Commit the obs_update.ref branch to the obs_update.project OBS project.",
    )
    parser_update.add_argument("--push", action="store_true", help=push_help)

    subparsers.add_parser(
        "check-builds",
        help="Check for failed builds in the OBS and IBS source projects.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    config = MakerConfig.from_file(Path(args.config))
    if args.fork_org:
        config.gitea_submissions.fork_org = args.fork_org
        for pkg_cfg in config.package_submissions.values():
            if pkg_cfg.gitea_submit:
                pkg_cfg.gitea_submit.fork_org = args.fork_org
    maker = ReleaseMaker(config)

    try:
        run_subcommand(args, parser, config, maker)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        # the output of failed commands is already logged by _run_command
        logging.debug("Details:", exc_info=True)
        if isinstance(e, subprocess.CalledProcessError):
            logging.error(f"Stopped, command failed: {format_cmd(list(e.cmd))}")
        else:
            logging.error(f"Stopped: {e}")
        if not args.verbose:
            logging.error("Use -v to see more details")
        sys.exit(1)
    finally:
        maker.print_summary()


def run_subcommand(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    config: MakerConfig,
    maker: ReleaseMaker,
) -> None:
    """Runs the subcommand selected on the command line."""
    if args.command == "obs-submit":
        maker.submit_to_obs(args.packages)
    elif args.command == "gitea-submit":
        maker.submit_to_gitea(args.packages)
    elif args.command == "bump-version":
        UpstreamRelease(maker._run_command).bump_version(args.version, args.push)
    elif args.command == "tag-release":
        UpstreamRelease(maker._run_command).tag_release(
            args.version, args.push, args.force
        )
    elif args.command == "publish-release":
        ObsUpdater(maker._run_command).update(
            args.ref or f"v{args.version}", RELEASE_PROJECT, args.push
        )
    elif args.command == "obs-update":
        if not config.obs_update:
            parser.error(f"No obs_update in {args.config}")
        # the maintenance branches stay mapped to their projects
        ObsUpdater(maker._run_command).update(
            config.obs_update.ref,
            config.obs_update.project,
            args.push,
            keep_mapping=True,
        )
    elif args.command == "check-builds":
        if not maker.check_builds():
            sys.exit(1)


if __name__ == "__main__":
    main()
