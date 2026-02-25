from pathlib import Path
from unittest.mock import MagicMock, patch, call, ANY
import pytest  # type: ignore
import subprocess

from agama_release_checker.reports.gitea_report import PackagesInGiteaReport


@patch(
    "agama_release_checker.reports.gitea_report.PackagesInGiteaReport._run_git_command"
)
@patch("agama_release_checker.reports.gitea_report.Path.exists")
@patch("agama_release_checker.reports.gitea_report.Path.read_text")
@patch("agama_release_checker.reports.gitea_report.ensure_dir")
def test_packages_in_gitea_report(
    mock_ensure_dir, mock_read_text, mock_exists, mock_run_git
):
    # Setup mocks
    # For exists, we want it to return True for the repo and the files
    mock_exists.return_value = True

    # We'll use side_effect for read_text to provide different content for different files
    # The first call is for agama.obsinfo, second for agama.spec
    mock_read_text.side_effect = [
        "version: 1.2.3\n",  # agama.obsinfo
        "Version: 1.2.3\nRelease: 1\n",  # agama.spec
    ]

    # Mock return values for _run_git_command
    # Assumes repo exists (mock_exists=True), so clone/init (first block) are skipped.
    # But now we added fetch/reset/init logic to the else block.
    # 1. fetch (success)
    # 2. reset --hard (success)
    # 3. sparse-checkout init (success)
    # 4. ls-tree (success, returns file list)
    # 5. sparse-checkout set (success)
    mock_run_git.side_effect = [
        (True, ""),  # fetch
        (True, ""),  # reset
        (True, ""),  # init --no-cone
        (True, "agama.obsinfo\nagama.spec\nother.file"),  # ls-tree
        (True, ""),  # sparse-checkout set
    ]

    config = {
        "url": "https://src.suse.de/pool/",
        "name": "ibs-pool",
    }
    # Only one package in rpm_map for this test
    rpm_map = {
        "agama": ["agama"],
    }
    specs_map = {}

    report = PackagesInGiteaReport(config, rpm_map, specs_map)
    _, packages = report.run()

    assert packages is not None
    assert len(packages) == 1
    assert packages[0].name == "agama"
    assert packages[0].version == "1.2.3"
    assert packages[0].release == "1"

    # Verify git sparse-checkout was called with --no-cone and correct files
    # The last call to _run_git_command should be the sparse-checkout set
    mock_run_git.assert_called_with(
        ["git", "sparse-checkout", "set", "--no-cone", "agama.obsinfo", "agama.spec"],
        cwd=ANY,
    )


def test_get_remote_url():
    config = {
        "url": "https://src.suse.de/pool/",
        "name": "ibs-pool",
    }
    report = PackagesInGiteaReport(config, {}, {})
    remote_url = report._get_remote_url("agama")
    assert remote_url == "gitea@src.suse.de:pool/agama.git"


@patch(
    "agama_release_checker.reports.gitea_report.PackagesInGiteaReport._run_git_command"
)
@patch("agama_release_checker.reports.gitea_report.Path.exists")
@patch("agama_release_checker.reports.gitea_report.ensure_dir")
def test_gitea_clone_with_branch(mock_ensure_dir, mock_exists, mock_run_git):
    # Repo does not exist
    mock_exists.return_value = False

    # Mock git command results
    # 1. clone (success)
    # 2. sparse-checkout init (success)
    # 3. ls-tree (success, empty) - stops here
    mock_run_git.side_effect = [
        (True, ""),
        (True, ""),
        (True, ""),
    ]

    config = {
        "url": "https://src.suse.de/pool/",
        "name": "ibs-pool",
        "branch": "mybranch",
    }
    rpm_map = {"agama": ["agama"]}
    report = PackagesInGiteaReport(config, rpm_map, {})

    report.run()

    # Verify clone command has --branch mybranch
    # Use ANY for path arguments to avoid constructing complex path checks
    mock_run_git.assert_any_call(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--sparse",
            "--depth",
            "1",
            "--branch",
            "mybranch",
            "gitea@src.suse.de:pool/agama.git",
            ANY,  # repo path
        ]
    )


@patch(
    "agama_release_checker.reports.gitea_report.PackagesInGiteaReport._run_git_command"
)
@patch("agama_release_checker.reports.gitea_report.Path.exists")
def test_gitea_update_with_branch(mock_exists, mock_run_git):
    # Repo exists
    mock_exists.return_value = True

    # Mock git command results
    # 1. fetch (success)
    # 2. reset (success)
    # 3. init (success)
    # 4. ls-tree (success, empty)
    mock_run_git.side_effect = [
        (True, ""),
        (True, ""),
        (True, ""),
        (True, ""),
    ]

    config = {
        "url": "https://src.suse.de/pool/",
        "name": "ibs-pool",
        "branch": "mybranch",
    }
    rpm_map = {"agama": ["agama"]}
    report = PackagesInGiteaReport(config, rpm_map, {})

    report.run()

    # Verify fetch command has branch
    mock_run_git.assert_any_call(
        ["git", "fetch", "--depth", "1", "origin", "mybranch"],
        cwd=ANY,
    )
