from unittest.mock import MagicMock

import pytest

from agama_release_checker.builds import BuildWaiter
from tests.test_upstream import completed

SRC = '<directory name="agama" srcmd5="new"/>'


def result_xml(*statuses: tuple[str, str, str]) -> str:
    """<resultlist> with (repository/arch, package, code) statuses."""
    results = []
    for where, package, code in statuses:
        repo, arch = where.split("/")
        results.append(
            f'<result repository="{repo}" arch="{arch}" state="published">'
            f'<status package="{package}" code="{code}"/></result>'
        )
    return "<resultlist>" + "".join(results) + "</resultlist>"


def job_xml(srcmd5: str, code: str = "succeeded") -> str:
    return f'<jobhistlist><jobhist srcmd5="{srcmd5}" code="{code}"/></jobhistlist>'


def api_runner(results: str, jobs: dict[str, str]) -> MagicMock:
    """Answers `osc api` calls: sources, results and job history by repo/arch."""

    def run(cmd, cwd=None, input=None):
        path = cmd[-1]
        if path.startswith("/source/"):
            return completed(SRC)
        if "/_result" in path:
            return completed(results)
        if "/_jobhistory" in path:
            repo_arch = "/".join(path.split("/")[3:5])
            return completed(jobs.get(repo_arch, "<jobhistlist/>"))
        raise AssertionError(path)

    return MagicMock(side_effect=run)


def test_status_current_and_old_sources():
    results = result_xml(
        ("TW/x86_64", "agama", "succeeded"),
        ("TW/aarch64", "agama", "succeeded"),
        ("TW/s390x", "agama", "excluded"),
    )
    jobs = {"TW/x86_64": job_xml("new"), "TW/aarch64": job_xml("old")}
    waiter = BuildWaiter(api_runner(results, jobs))

    pending, failed = waiter.status(None, "prj", ["agama"])

    # aarch64 shows the result of the old sources
    assert pending == ["agama TW/aarch64 (succeeded)"]
    assert failed == []


def test_status_rebuild_of_built_sources_is_not_pending():
    """A rebuild (e.g. blocked by a dependency) of already built sources."""
    results = result_xml(("images/x86_64", "agama-installer:SLES", "blocked"))
    jobs = {"images/x86_64": job_xml("new", "unchanged")}
    pending, failed = BuildWaiter(api_runner(results, jobs)).status(
        None, "prj", ["agama-installer"]
    )
    assert (pending, failed) == ([], [])


def test_status_failures_and_ignore():
    results = result_xml(
        ("TW/ppc64le", "agama", "failed"),
        ("TW/x86_64", "agama", "unresolvable"),
    )
    jobs = {"TW/ppc64le": job_xml("new", "failed")}

    _, failed = BuildWaiter(api_runner(results, jobs)).status(None, "p", ["agama"])
    assert failed == ["agama TW/ppc64le (failed)", "agama TW/x86_64 (unresolvable)"]

    waiter = BuildWaiter(api_runner(results, jobs), ignore=["agama */ppc64le"])
    _, failed = waiter.status(None, "p", ["agama"])
    assert failed == ["agama TW/x86_64 (unresolvable)"]


def test_status_old_failure_is_pending():
    results = result_xml(("TW/x86_64", "agama", "failed"))
    jobs = {"TW/x86_64": job_xml("old", "failed")}
    pending, failed = BuildWaiter(api_runner(results, jobs)).status(
        None, "p", ["agama"]
    )
    assert (pending, failed) == (["agama TW/x86_64 (failed)"], [])


def test_status_uses_api():
    run = api_runner(result_xml(), {})
    BuildWaiter(run).status("https://api.suse.de", "p", ["agama"])
    assert run.call_args_list[0].args[0][:3] == ["osc", "-A", "https://api.suse.de"]


def test_wait_until_built():
    results = result_xml(("TW/x86_64", "agama", "building"))
    jobs = {"TW/x86_64": job_xml("old")}
    run = api_runner(results, jobs)
    sleeps = []

    def sleep(seconds):
        # the build finishes while sleeping
        sleeps.append(seconds)
        jobs["TW/x86_64"] = job_xml("new")

    BuildWaiter(run, sleep=sleep).wait([(None, "p")], ["agama"])
    assert len(sleeps) == 1


def test_wait_failed():
    results = result_xml(("TW/x86_64", "agama", "failed"))
    run = api_runner(results, {"TW/x86_64": job_xml("new", "failed")})
    with pytest.raises(RuntimeError, match="p: agama TW/x86_64"):
        BuildWaiter(run, sleep=lambda _: None).wait([(None, "p")], ["agama"])


def test_wait_timeout():
    results = result_xml(("TW/x86_64", "agama", "scheduled"))
    run = api_runner(results, {})
    with pytest.raises(RuntimeError, match="Timeout"):
        BuildWaiter(run, sleep=lambda _: None, timeout=0).wait([(None, "p")], ["agama"])
