"""Preparing and tagging a versioned Agama release in the upstream Git repo."""

import datetime
import json
import logging
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

UPSTREAM_REPO = "git@github.com:agama-project/agama.git"
GITHUB_REPO = "agama-project/agama"
BASE_BRANCH = "master"

# The .changes files of the packages built from the upstream repo
CHANGES_FILES = [
    "rust/package/agama.changes",
    "service/package/rubygem-agama-yast.changes",
    "web/package/agama-web-ui.changes",
    "products.d/agama-products.changes",
    "live/src/agama-installer.changes",
]
KIWI_FILE = "live/src/agama-installer.kiwi"
GEMFILE_LOCK = "service/Gemfile.lock"

# The GitHub workflows committing the packages to OBS, see devel/branch2obs.sh
OBS_WORKFLOWS = [
    "obs-staging-live.yml",
    "obs-staging-products.yml",
    "obs-staging-rust.yml",
    "obs-staging-service.yml",
    "obs-staging-web.yml",
]
# GitHub variable mapping Git refs to OBS projects, read by the workflows
OBS_PROJECTS_VAR = "OBS_PROJECTS"

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]

Runner = Callable[..., subprocess.CompletedProcess[str]]


def changes_date(now: datetime.datetime) -> str:
    """Formats a UTC time like `osc vc` does, independently of the locale.

    >>> changes_date(datetime.datetime(2026, 9, 1, 15, 51, 10))
    'Tue Sep  1 15:51:10 UTC 2026'
    """
    return (
        f"{_DAYS[now.weekday()]} {_MONTHS[now.month - 1]} {now.day:2d}"
        f" {now:%H:%M:%S} UTC {now.year}"
    )


def changes_entry(version: str, name: str, email: str, now: datetime.datetime) -> str:
    """Returns a .changes entry announcing the given version."""
    return (
        "-" * 67
        + "\n"
        + f"{changes_date(now)} - {name} <{email}>\n"
        + "\n"
        + f"- Version {version}\n"
        + "\n"
    )


def bump_kiwi(text: str, version: str) -> str:
    """Sets the image version in a kiwi file.

    >>> bump_kiwi("  <version>23.0.0</version>", "24")
    '  <version>24.0.0</version>'
    """
    new_text, count = re.subn(
        r"<version>[^<]*</version>", f"<version>{version}.0.0</version>", text, count=1
    )
    if count != 1:
        raise ValueError("No <version> element found in the kiwi file")
    return new_text


def bump_gemfile_lock(text: str, version: str) -> str:
    """Sets the agama-yast version in Gemfile.lock.

    >>> bump_gemfile_lock("  specs:\\n    agama-yast (23)\\n", "24")
    '  specs:\\n    agama-yast (24)\\n'
    """
    new_text, count = re.subn(
        r"^(\s+agama-yast) \([^)]*\)$",
        rf"\1 ({version})",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError("No agama-yast entry found in Gemfile.lock")
    return new_text


def merged_prs(subjects: list[str]) -> list[str]:
    """Extracts PR references from merge commit subjects, oldest first.

    `git log` lists the newest first.

    >>> merged_prs(["Fix b (#12)", "Merge pull request #11 from x/y", "No PR"])
    ['#11', '#12']
    """
    prs = []
    for subject in reversed(subjects):
        match = re.search(r"\(#(\d+)\)$", subject) or re.match(
            r"Merge pull request #(\d+)", subject
        )
        if match:
            prs.append(f"#{match.group(1)}")
    return prs


def pr_body(version: str, prs: list[str]) -> str:
    """Returns the description of the release PR."""
    lines = [f"Prepare to release version {version}:", ""]
    lines += [f"* {pr}" for pr in prs]
    return "\n".join(lines)


class UpstreamRelease:
    """Prepares and tags a versioned release in the upstream Agama repo.

    Responsibilities:
    - bumping the version (.changes, kiwi, Gemfile.lock) in a release PR
    - tagging the merged release PR once its CI has passed

    Works in a fresh temporary clone. Nothing is pushed unless `push` is set.
    """

    def __init__(
        self,
        run: Runner,
        repo: str = UPSTREAM_REPO,
        github_repo: str = GITHUB_REPO,
        base: str = BASE_BRANCH,
    ):
        """Initializes with a command runner (like `ReleaseMaker._run_command`)."""
        self.run = run
        self.repo = repo
        self.github_repo = github_repo
        self.base = base

    @staticmethod
    def branch_name(version: str) -> str:
        """Returns the name of the release PR branch."""
        return f"release-{version}"

    def _clone(self, tmp_path: Path) -> Path:
        """Clones the base branch of the upstream repo."""
        repo_dir = tmp_path / "agama"
        self.run(
            ["git", "clone", "--branch", self.base, self.repo, str(repo_dir)],
        )
        return repo_dir

    def _git_config(self, repo_dir: Path, key: str) -> str:
        """Returns a git config value."""
        return self.run(["git", "config", key], cwd=repo_dir).stdout.strip()

    def _open_pr_exists(self, branch: str) -> bool:
        """Checks if an open GitHub PR exists for the branch."""
        res = self.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.github_repo,
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "url",
            ]
        )
        prs = json.loads(res.stdout)
        if prs:
            logging.info(f"Pull request already exists: {prs[0]['url']}")
        return bool(prs)

    def apply_bump(self, repo_dir: Path, version: str, name: str, email: str) -> None:
        """Edits the files of a checkout to announce the given version."""
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = changes_entry(version, name, email, now)
        for changes in CHANGES_FILES:
            path = repo_dir / changes
            path.write_text(entry + path.read_text())

        kiwi = repo_dir / KIWI_FILE
        kiwi.write_text(bump_kiwi(kiwi.read_text(), version))

        lock = repo_dir / GEMFILE_LOCK
        lock.write_text(bump_gemfile_lock(lock.read_text(), version))

    def bump_version(self, version: str, push: bool = False) -> None:
        """Creates the release commit and, with `push`, the release PR.

        Without `push`, the temporary clone is kept for inspection.
        """
        branch = self.branch_name(version)
        if push and self._open_pr_exists(branch):
            return

        temp_obj = tempfile.TemporaryDirectory(
            prefix="agama-release-maker-", delete=False
        )
        repo_dir = self._clone(Path(temp_obj.name))

        previous_tag = self.run(
            ["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"],
            cwd=repo_dir,
        ).stdout.strip()
        log = self.run(
            ["git", "log", "--first-parent", "--format=%s", f"{previous_tag}..HEAD"],
            cwd=repo_dir,
        ).stdout
        body = pr_body(version, merged_prs(log.splitlines()))

        self.run(["git", "checkout", "-b", branch], cwd=repo_dir)
        name = self._git_config(repo_dir, "user.name")
        email = self._git_config(repo_dir, "user.email")
        self.apply_bump(repo_dir, version, name, email)

        title = f"Release version {version}"
        self.run(["git", "commit", "-a", "-m", title], cwd=repo_dir)

        if not push:
            stat = self.run(["git", "show", "--stat"], cwd=repo_dir).stdout
            print(stat)
            print(body)
            logging.info(f"Dry run, not pushing. Inspect {repo_dir}")
            return

        self.run(["git", "push", "origin", branch], cwd=repo_dir)
        self.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                self.github_repo,
                "--base",
                self.base,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ],
            cwd=repo_dir,
        )
        temp_obj.cleanup()

    def merged_commit(self, version: str) -> str:
        """Returns the merge commit of the release PR; fails if not merged."""
        res = self.run(
            [
                "gh",
                "pr",
                "view",
                self.branch_name(version),
                "--repo",
                self.github_repo,
                "--json",
                "state,mergeCommit",
            ]
        )
        pr = json.loads(res.stdout)
        if pr["state"] != "MERGED":
            raise RuntimeError(f"The release PR is not merged (state: {pr['state']})")
        return str(pr["mergeCommit"]["oid"])

    def failed_runs(self, sha: str) -> list[str]:
        """Returns names of GitHub workflow runs for the commit that did not succeed."""
        res = self.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                self.github_repo,
                "--commit",
                sha,
                "--json",
                "name,status,conclusion",
            ]
        )
        runs = json.loads(res.stdout)
        return [
            f"{r['name']} ({r['conclusion'] or r['status']})"
            for r in runs
            if r["conclusion"] not in ("success", "skipped")
        ]

    def tag_release(
        self, version: str, push: bool = False, force: bool = False
    ) -> None:
        """Tags the merged release PR with a signed tag and, with `push`, pushes it."""
        sha = self.merged_commit(version)
        failed = self.failed_runs(sha)
        if failed:
            message = f"CI did not pass for {sha}: {', '.join(failed)}"
            if not force:
                raise RuntimeError(message)
            logging.warning(message)

        temp_obj = tempfile.TemporaryDirectory(
            prefix="agama-release-maker-", delete=False
        )
        repo_dir = self._clone(Path(temp_obj.name))
        tag = f"v{version}"
        self.run(
            ["git", "tag", "-s", tag, "-m", f"Version {version}", sha], cwd=repo_dir
        )

        if not push:
            logging.info(f"Dry run, not pushing tag {tag}. Inspect {repo_dir}")
            return

        self.run(["git", "push", "origin", tag], cwd=repo_dir)
        temp_obj.cleanup()


class ObsUpdater:
    """Commits the packages of an upstream Git ref to an OBS project.

    Does what `devel/branch2obs.sh -b REF -p PROJECT` does for an existing
    project: maps REF to PROJECT in the OBS_PROJECTS GitHub variable and runs
    the OBS_WORKFLOWS on REF. Additionally, it waits for the workflows to finish
    and, unless `keep_mapping` is set, restores the previous mapping afterwards.
    """

    def __init__(
        self,
        run: Runner,
        github_repo: str = GITHUB_REPO,
        poll_interval: float = 30,
        timeout: float = 3600,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.run = run
        self.github_repo = github_repo
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep

    def get_mapping(self) -> dict[str, str]:
        """Returns the OBS_PROJECTS GitHub variable."""
        res = self.run(
            ["gh", "variable", "get", OBS_PROJECTS_VAR, "--repo", self.github_repo]
        )
        mapping: dict[str, str] = json.loads(res.stdout or "{}")
        return mapping

    def set_mapping(self, mapping: dict[str, str]) -> None:
        """Sets the OBS_PROJECTS GitHub variable."""
        self.run(
            [
                "gh",
                "variable",
                "set",
                OBS_PROJECTS_VAR,
                "--repo",
                self.github_repo,
                "--body",
                json.dumps(mapping),
            ]
        )

    def _map(self, ref: str, project: str | None) -> None:
        """Maps ref to project (or removes the mapping), re-reading the variable."""
        mapping = self.get_mapping()
        if project is None:
            mapping.pop(ref, None)
        else:
            mapping[ref] = project
        self.set_mapping(mapping)

    def check_ref_exists(self, ref: str) -> None:
        """Fails if the branch or tag does not exist upstream."""
        res = self.run(
            [
                "git",
                "ls-remote",
                f"https://github.com/{self.github_repo}.git",
                f"refs/heads/{ref}",
                f"refs/tags/{ref}",
            ]
        )
        if not res.stdout.strip():
            raise RuntimeError(f"No branch or tag {ref} in {self.github_repo}")

    def _latest_run(self, workflow: str, ref: str, since: str) -> dict[str, Any] | None:
        """Returns the newest dispatched run of a workflow for ref since a time."""
        res = self.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                self.github_repo,
                "--workflow",
                workflow,
                "--branch",
                ref,
                "--event",
                "workflow_dispatch",
                "--limit",
                "5",
                "--json",
                "databaseId,status,conclusion,createdAt,url",
            ]
        )
        # ISO 8601 UTC timestamps compare correctly as strings
        runs: list[dict[str, Any]] = [
            r for r in json.loads(res.stdout) if r["createdAt"] >= since
        ]
        return max(runs, key=lambda r: r["createdAt"]) if runs else None

    def wait_for_runs(self, ref: str, since: str) -> None:
        """Waits until the OBS_WORKFLOWS dispatched since a time finish.

        Raises if some of them did not succeed or the timeout is reached.
        """
        pending = list(OBS_WORKFLOWS)
        failed: list[str] = []
        waited = 0.0
        while True:
            for workflow in list(pending):
                run = self._latest_run(workflow, ref, since)
                if run and run["status"] == "completed":
                    pending.remove(workflow)
                    logging.info(f"{workflow}: {run['conclusion']} {run['url']}")
                    if run["conclusion"] not in ("success", "skipped"):
                        failed.append(f"{workflow} ({run['conclusion']}) {run['url']}")
            if not pending:
                break
            if waited >= self.timeout:
                raise RuntimeError(f"Timeout waiting for {', '.join(pending)}")
            logging.info(f"Waiting for {', '.join(pending)}")
            self.sleep(self.poll_interval)
            waited += self.poll_interval

        if failed:
            raise RuntimeError("OBS workflows failed:\n" + "\n".join(failed))

    def update(
        self, ref: str, project: str, push: bool = False, keep_mapping: bool = False
    ) -> None:
        """Runs the OBS workflows for ref, committing to project."""
        self.check_ref_exists(ref)
        previous = self.get_mapping().get(ref)
        change_mapping = previous != project
        if change_mapping:
            logging.info(f"{ref} is mapped to {previous}, mapping it to {project}")

        if not push:
            logging.info(
                f"Dry run, would run {', '.join(OBS_WORKFLOWS)} on {ref} for {project}"
            )
            return

        if change_mapping:
            self._map(ref, project)
        try:
            # a minute back, to tolerate clock differences with GitHub
            since = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=1)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            for workflow in OBS_WORKFLOWS:
                self.run(
                    [
                        "gh",
                        "workflow",
                        "run",
                        workflow,
                        "--repo",
                        self.github_repo,
                        "--ref",
                        ref,
                    ]
                )
            # let GitHub register the runs
            self.sleep(self.poll_interval)
            self.wait_for_runs(ref, since)
        finally:
            if change_mapping and not keep_mapping:
                logging.info(f"Restoring the mapping of {ref} to {previous}")
                self._map(ref, previous)
        logging.info(f"{project} updated from {ref}, check its builds now")
