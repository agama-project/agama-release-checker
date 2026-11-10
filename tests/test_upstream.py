import datetime
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agama_release_checker.upstream import (
    CHANGES_FILES,
    GEMFILE_LOCK,
    KIWI_FILE,
    OBS_WORKFLOWS,
    ObsUpdater,
    UpstreamRelease,
    bump_gemfile_lock,
    bump_kiwi,
    changes_entry,
    merged_prs,
    pr_body,
)


def completed(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)


def test_changes_entry():
    now = datetime.datetime(2026, 9, 1, 15, 51, 10)
    entry = changes_entry("24", "Jane Doe", "jdoe@example.com", now)
    assert entry == (
        "-" * 67
        + "\nTue Sep  1 15:51:10 UTC 2026 - Jane Doe <jdoe@example.com>\n"
        + "\n- Version 24\n\n"
    )


def test_bump_kiwi_only_first_version():
    text = "<version>23.0.0</version>\n<version>1.0</version>"
    assert bump_kiwi(text, "24") == "<version>24.0.0</version>\n<version>1.0</version>"


def test_bump_kiwi_missing():
    with pytest.raises(ValueError):
        bump_kiwi("<image/>", "24")


def test_bump_gemfile_lock():
    text = "PATH\n  specs:\n    agama-yast (23)\n      cfa (~> 1.0.2)\n"
    assert bump_gemfile_lock(text, "24") == (
        "PATH\n  specs:\n    agama-yast (24)\n      cfa (~> 1.0.2)\n"
    )


def test_bump_gemfile_lock_missing():
    with pytest.raises(ValueError):
        bump_gemfile_lock("  specs:\n    other (1)\n", "24")


def test_merged_prs_and_body():
    subjects = ["Release version 24 (#3857)", "Some direct commit", "Fix (#3739)"]
    prs = merged_prs(subjects)
    assert prs == ["#3739", "#3857"]
    assert pr_body("25", prs) == ("Prepare to release version 25:\n\n* #3739\n* #3857")


def make_checkout(root: Path) -> None:
    for changes in CHANGES_FILES:
        path = root / changes
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("-" * 67 + "\nold entry\n")
    (root / KIWI_FILE).write_text("    <version>24.0.0</version>\n")
    (root / GEMFILE_LOCK).write_text("  specs:\n    agama-yast (24)\n")


def test_apply_bump(tmp_path):
    make_checkout(tmp_path)
    UpstreamRelease(MagicMock()).apply_bump(tmp_path, "25", "Jane", "j@example.com")

    for changes in CHANGES_FILES:
        text = (tmp_path / changes).read_text()
        assert "Jane <j@example.com>\n\n- Version 25\n\n" + "-" * 67 in text
        assert text.endswith("old entry\n")
    assert "<version>25.0.0</version>" in (tmp_path / KIWI_FILE).read_text()
    assert "agama-yast (25)" in (tmp_path / GEMFILE_LOCK).read_text()


def fake_runner(tmp_path: Path, gh_outputs: dict[str, str] | None = None) -> MagicMock:
    """A runner that creates a fake checkout on clone and answers queries."""
    gh_outputs = gh_outputs or {}

    def run(cmd, cwd=None, input=None):
        if cmd[:2] == ["git", "clone"]:
            make_checkout(Path(cmd[-1]))
        elif cmd[:2] == ["git", "describe"]:
            return completed("v24\n")
        elif cmd[:2] == ["git", "log"]:
            return completed("Fix (#3901)\nFeature (#3900)\n")
        elif cmd[:2] == ["git", "config"]:
            return completed("value\n")
        elif cmd[0] == "gh":
            return completed(gh_outputs.get(cmd[2], "[]"))
        return completed()

    return MagicMock(side_effect=run)


def commands(run: MagicMock) -> list[list[str]]:
    return [call.args[0] for call in run.call_args_list]


@patch("agama_release_checker.upstream.tempfile.TemporaryDirectory")
def test_bump_version_dry_run(mock_tmp, tmp_path):
    mock_tmp.return_value.name = str(tmp_path)
    run = fake_runner(tmp_path)

    UpstreamRelease(run).bump_version("25")

    cmds = commands(run)
    assert ["git", "checkout", "-b", "release-25"] in cmds
    assert ["git", "commit", "-a", "-m", "Release version 25"] in cmds
    assert not any(c[:2] == ["git", "push"] or c[0] == "gh" for c in cmds)
    assert "agama-yast (25)" in (tmp_path / "agama" / GEMFILE_LOCK).read_text()
    mock_tmp.return_value.cleanup.assert_not_called()


@patch("agama_release_checker.upstream.tempfile.TemporaryDirectory")
def test_bump_version_push(mock_tmp, tmp_path):
    mock_tmp.return_value.name = str(tmp_path)
    run = fake_runner(tmp_path)

    UpstreamRelease(run).bump_version("25", push=True)

    cmds = commands(run)
    assert ["git", "push", "origin", "release-25"] in cmds
    create = [c for c in cmds if c[:3] == ["gh", "pr", "create"]][0]
    body = create[create.index("--body") + 1]
    assert body == "Prepare to release version 25:\n\n* #3900\n* #3901"


def test_bump_version_existing_pr(tmp_path):
    run = fake_runner(tmp_path, {"list": json.dumps([{"url": "http://pr"}])})

    UpstreamRelease(run).bump_version("25", push=True)

    assert not any(c[:2] == ["git", "clone"] for c in commands(run))


def test_tag_release_not_merged(tmp_path):
    run = fake_runner(
        tmp_path, {"view": json.dumps({"state": "OPEN", "mergeCommit": None})}
    )
    with pytest.raises(RuntimeError, match="not merged"):
        UpstreamRelease(run).tag_release("25", push=True)


MERGED = json.dumps({"state": "MERGED", "mergeCommit": {"oid": "abc123"}})


def test_tag_release_failed_ci(tmp_path):
    runs = [
        {"name": "CI - Rust", "status": "completed", "conclusion": "failure"},
        {"name": "CI - Web", "status": "completed", "conclusion": "success"},
    ]
    run = fake_runner(tmp_path, {"view": MERGED, "list": json.dumps(runs)})
    with pytest.raises(RuntimeError, match="CI - Rust"):
        UpstreamRelease(run).tag_release("25", push=True)


@patch("agama_release_checker.upstream.tempfile.TemporaryDirectory")
def test_tag_release_push(mock_tmp, tmp_path):
    mock_tmp.return_value.name = str(tmp_path)
    runs = [{"name": "CI - Web", "status": "completed", "conclusion": "success"}]
    run = fake_runner(tmp_path, {"view": MERGED, "list": json.dumps(runs)})

    UpstreamRelease(run).tag_release("25", push=True)

    cmds = commands(run)
    assert ["git", "tag", "-s", "v25", "-m", "Version 25", "abc123"] in cmds
    assert ["git", "push", "origin", "v25"] in cmds


def obs_runner(
    mapping: dict[str, str],
    run_conclusion: str = "success",
    ls_remote: str = "abc refs/tags/v25\n",
) -> tuple[MagicMock, dict[str, dict[str, str]]]:
    """A runner simulating the OBS_PROJECTS variable and the workflow runs."""
    state: dict[str, dict[str, str]] = {"mapping": dict(mapping)}

    def run(cmd, cwd=None, input=None):
        if cmd[:3] == ["gh", "variable", "get"]:
            return completed(json.dumps(state["mapping"]))
        if cmd[:3] == ["gh", "variable", "set"]:
            state["mapping"] = json.loads(cmd[cmd.index("--body") + 1])
        elif cmd[:3] == ["gh", "run", "list"]:
            runs = [
                {
                    "databaseId": 1,
                    "status": "completed",
                    "conclusion": run_conclusion,
                    "createdAt": "2999-01-01T00:00:00Z",
                    "url": "http://run",
                }
            ]
            return completed(json.dumps(runs))
        elif cmd[:2] == ["git", "ls-remote"]:
            return completed(ls_remote)
        return completed()

    mock = MagicMock(side_effect=run)
    return mock, state


def updater(run: MagicMock) -> ObsUpdater:
    return ObsUpdater(run, sleep=lambda _: None)


def test_obs_update_dry_run():
    run, state = obs_runner({"master": "Devel"})
    updater(run).update("v25", "Release")

    cmds = commands(run)
    assert not any(c[:3] == ["gh", "variable", "set"] for c in cmds)
    assert not any(c[:3] == ["gh", "workflow", "run"] for c in cmds)


def test_obs_update_missing_ref():
    run, _ = obs_runner({}, ls_remote="")
    with pytest.raises(RuntimeError, match="No branch or tag v25"):
        updater(run).update("v25", "Release", push=True)


def test_obs_update_temporary_mapping():
    run, state = obs_runner({"master": "Devel"})
    updater(run).update("v25", "Release", push=True)

    cmds = commands(run)
    dispatched = [c[3] for c in cmds if c[:3] == ["gh", "workflow", "run"]]
    assert dispatched == OBS_WORKFLOWS
    assert all(
        c[-2:] == ["--ref", "v25"] for c in cmds if c[:3] == ["gh", "workflow", "run"]
    )
    # v25 was mapped, then the mapping removed again
    sets = [json.loads(c[-1]) for c in cmds if c[:3] == ["gh", "variable", "set"]]
    assert sets == [{"master": "Devel", "v25": "Release"}, {"master": "Devel"}]
    assert state["mapping"] == {"master": "Devel"}


def test_obs_update_existing_mapping_kept():
    run, state = obs_runner({"SLE-16.1": "Maint"})
    updater(run).update("SLE-16.1", "Maint", push=True, keep_mapping=True)

    assert not any(c[:3] == ["gh", "variable", "set"] for c in commands(run))


def test_obs_update_failed_restores_mapping():
    run, state = obs_runner({"master": "Devel"}, run_conclusion="failure")
    with pytest.raises(RuntimeError, match="OBS workflows failed"):
        updater(run).update("master", "Release", push=True)
    assert state["mapping"] == {"master": "Devel"}


def test_obs_update_timeout():
    run, state = obs_runner({})
    obs = ObsUpdater(run, sleep=lambda _: None, timeout=0)
    obs._latest_run = MagicMock(return_value=None)  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Timeout"):
        obs.update("v25", "Release", push=True)
    assert state["mapping"] == {}
