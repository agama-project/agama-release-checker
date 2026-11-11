"""Waiting for OBS/IBS builds of the current sources to finish."""

import fnmatch
import logging
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import quote

Runner = Callable[..., subprocess.CompletedProcess[str]]

# Build status codes (osc results) for which no build is expected
SKIPPED = {"disabled", "excluded", "locked"}
# Build status codes meaning a failure without a build job
UNBUILDABLE = {"unresolvable", "broken"}
# Job history codes of successful builds
SUCCEEDED_JOBS = {"succeeded", "unchanged"}


class BuildWaiter:
    """Checks and waits for the builds of some packages in OBS projects.

    A build counts as finished when its last job used the current sources of
    the package (same srcmd5). This way:
    - the results of the previous sources are not taken for the new ones, e.g.,
      in an IBS project that has not noticed yet that the sources of the OBS
      project it links to changed;
    - a rebuild of the current sources (e.g., triggered by a changed dependency
      in Tumbleweed) does not need to be waited for if they already built.

    Builds matching one of the `ignore` patterns ("package repository/arch",
    with shell wildcards, e.g. "agama */ppc64le") are not checked.
    """

    def __init__(
        self,
        run: Runner,
        poll_interval: float = 120,
        timeout: float = 4 * 3600,
        sleep: Callable[[float], None] = time.sleep,
        ignore: list[str] | None = None,
    ):
        self.ignore = ignore or []
        self.run = run
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.sleep = sleep

    def _api(self, api: str | None, path: str) -> ET.Element:
        """Calls the OBS API (`osc api`) and parses the XML answer."""
        cmd = ["osc"] + (["-A", api] if api else []) + ["api", path]
        return ET.fromstring(self.run(cmd).stdout)

    def _srcmd5(self, api: str | None, project: str, package: str) -> str:
        """Returns the srcmd5 of the expanded current sources of a package."""
        directory = self._api(api, f"/source/{project}/{package}?expand=1")
        return directory.get("srcmd5", "")

    def _last_job(
        self, api: str | None, project: str, repo: str, arch: str, package: str
    ) -> ET.Element | None:
        """Returns the last finished build job of a package, if any."""
        jobs = self._api(
            api,
            f"/build/{project}/{repo}/{arch}/_jobhistory"
            f"?package={quote(package)}&limit=1",
        )
        return jobs.find("jobhist")

    def status(
        self, api: str | None, project: str, packages: list[str]
    ) -> tuple[list[str], list[str]]:
        """Returns the (pending, failed) builds of the packages in a project.

        Both are lists of "package repository/arch (code)" descriptions.
        """
        pending: list[str] = []
        failed: list[str] = []
        for package in packages:
            srcmd5 = self._srcmd5(api, project, package)
            results = self._api(
                api,
                f"/build/{project}/_result?package={quote(package)}"
                "&multibuild=1&locallink=1",
            )
            for result in results.findall("result"):
                repo = result.get("repository", "")
                arch = result.get("arch", "")
                for status in result.findall("status"):
                    # multibuild flavors are reported as "package:flavor"
                    flavor = status.get("package", package)
                    code = status.get("code", "")
                    build = f"{flavor} {repo}/{arch}"
                    where = f"{build} ({code})"
                    if code in SKIPPED or self._ignored(build):
                        continue
                    if code in UNBUILDABLE:
                        failed.append(where)
                        continue
                    job = self._last_job(api, project, repo, arch, flavor)
                    if job is None or job.get("srcmd5") != srcmd5:
                        # not built yet, or the result of older sources
                        pending.append(where)
                    elif job.get("code") not in SUCCEEDED_JOBS:
                        failed.append(f"{build} ({job.get('code')})")
        return pending, failed

    def _ignored(self, build: str) -> bool:
        """Checks if a "package repository/arch" build is ignored."""
        return any(fnmatch.fnmatchcase(build, pattern) for pattern in self.ignore)

    def wait(self, projects: list[tuple[str | None, str]], packages: list[str]) -> None:
        """Waits until the builds in all the (API, project) pairs finish.

        Raises if some build failed or the timeout is reached.
        """
        waited = 0.0
        while True:
            all_pending: list[str] = []
            all_failed: list[str] = []
            for api, project in projects:
                pending, failed = self.status(api, project, packages)
                all_pending += [f"{project}: {p}" for p in pending]
                all_failed += [f"{project}: {f}" for f in failed]
            if all_failed:
                raise RuntimeError("Failed builds:\n" + "\n".join(all_failed))
            if not all_pending:
                logging.info("All builds finished")
                return
            if waited >= self.timeout:
                raise RuntimeError(
                    "Timeout waiting for builds:\n" + "\n".join(all_pending)
                )
            logging.info(
                f"Waiting for {len(all_pending)} builds, e.g. {all_pending[0]}"
            )
            self.sleep(self.poll_interval)
            waited += self.poll_interval
