import pytest
import json
import subprocess
from unittest.mock import patch, MagicMock, ANY
from agama_release_checker.maker import ReleaseMaker
from agama_release_checker.models import (
    MakerConfig,
    PackageSubmissionConfig,
    GiteaSubmitStrategy,
    ObsSubmissionsConfig,
    GiteaSubmissionsConfig,
)


@pytest.fixture
def mock_config():
    """Provides a mock MakerConfig with test packages."""
    config = MagicMock(spec=MakerConfig)
    config.package_submissions = {
        "pkg1": PackageSubmissionConfig(),
        "pkg2": PackageSubmissionConfig(),
    }
    config.obs_submissions = ObsSubmissionsConfig(
        source_project="source_proj", target_project="target_proj"
    )
    config.gitea_submissions = GiteaSubmissionsConfig(
        source_project="source_proj",
        target_org="target_org",
        target_branch="target_branch",
    )
    return config


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs(mock_run, mock_config):
    """Verifies that submit_to_obs calls osc sr with the correct arguments."""

    def run_side_effect(cmd, **kwargs):
        if "--diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "filterdiff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked changes diff", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    maker = ReleaseMaker(mock_config)
    maker.submit_to_obs([])

    # For each package (2 packages):
    # 1. osc sr --diff
    # 2. filterdiff
    # 3. osc sr
    assert mock_run.call_count == 6

    mock_run.assert_any_call(
        [
            "osc",
            "sr",
            "--yes",
            "-m",
            "Automatic update from source_proj\n\nMocked changes diff",
            "source_proj",
            "pkg1",
            "target_proj",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=None,
    )


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs_no_changes(mock_run, mock_config):
    """Verifies that submit_to_obs handles the 'no actions' error gracefully."""
    # Simulate the osc 400 error for no actions
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        ["osc", "sr"],
        output="",
        stderr="Server returned an error: HTTP Error 400: Bad Request\nThe request contains no actions. Submit requests without source changes may have skipped!",
    )

    maker = ReleaseMaker(mock_config)
    # This should NOT raise an exception
    maker.submit_to_obs(["pkg1", "pkg2"])

    assert mock_run.call_count == 4


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea performs the full sync and PR creation flow."""

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            # Return empty list to trigger PR creation
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    # Mock iterdir to avoid FileNotFoundError
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # For each package (2 packages):
    # 1. osc co (with -A)
    # 2. git clone
    # 3. git checkout -b
    # 4. iterdir + sync (mocked)
    # 5. git add
    # 6. git status
    # 7. git commit
    # 8. git push
    # 9. tea pr list
    # (PR creation adds another call if not filtered)
    assert mock_run.call_count >= 18

    mock_run.assert_any_call(
        ["osc", "-A", "https://api.suse.de", "co", "source_proj", "pkg1"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "git",
            "clone",
            "--branch",
            "target_branch",
            "gitea@src.suse.de:target_org/pkg1.git",
            ANY,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--repo",
            "target_org/pkg1",
            "--base",
            "target_branch",
            "--head",
            "target_org:target_branch-update",
            "--title",
            "Update from OBS source_proj",
            "--description",
            "Automatic update from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_fork(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea pushes to a fork if fork_org is provided."""
    mock_config.gitea_submissions.fork_org = "fork_org"

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # Verify push to fork
    mock_run.assert_any_call(
        ["git", "push", "fork", "target_branch-update", "--force"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )

    # Verify PR creation with fork head
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--repo",
            "target_org/pkg1",
            "--base",
            "target_branch",
            "--head",
            "fork_org:target_branch-update",
            "--title",
            "Update from OBS source_proj",
            "--description",
            "Automatic update from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )


@patch("agama_release_checker.maker.Path.iterdir")
@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.shutil.copy2")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_existing_pr(
    mock_run, mock_copy2, mock_copytree, mock_iterdir, mock_config
):
    """Verifies that submit_to_gitea skips PR creation if one already exists."""

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "pr" in cmd and "list" in cmd:
            # Return an existing PR
            return MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "head": "target_org:target_branch-update",
                            "base": "target_branch",
                            "url": "http://example.com/pr/1",
                        }
                    ]
                ),
                stderr="",
            )
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # Verify that tea pr create was NOT called
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert not (args[0] == "tea" and args[2] == "create")


@patch("agama_release_checker.maker.shutil.copytree")
@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_gitea_custom(mock_run, mock_copytree, mock_config):
    """Verifies that submit_to_gitea uses the custom strategy when provided."""
    strategy = GiteaSubmitStrategy(
        source_repo="https://github.com/org/repo",
        source_run="make build",
        source_dir="dist",
        target_repo="gitea@gitea.example.com:target_owner/target_repo.git",
        target_dir="subdir",
        target_branch="custom_branch",
    )
    mock_config.package_submissions = {
        "custom-pkg": PackageSubmissionConfig(gitea_submit=strategy)
    }

    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        if "diff" in cmd:
            return MagicMock(returncode=0, stdout="Mocked diff output", stderr="")
        if "pr" in cmd and "list" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea([])

    # 1. git clone source
    # 2. make build
    # 3. git clone target
    # 4. git checkout -b
    # 5. git add
    # 6. git status
    # 7. git commit
    # 8. git push
    # 9. tea pr list
    # 10. tea pr create
    assert mock_run.call_count >= 10

    mock_run.assert_any_call(
        ["git", "clone", "https://github.com/org/repo", ANY],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        ["make", "build"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "git",
            "clone",
            "--branch",
            "custom_branch",
            "gitea@gitea.example.com:target_owner/target_repo.git",
            ANY,
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
        input=ANY,
    )
    mock_run.assert_any_call(
        [
            "tea",
            "pr",
            "create",
            "--repo",
            "target_owner/target_repo",
            "--base",
            "custom_branch",
            "--head",
            "target_owner:custom_branch-update-custom-pkg",
            "--title",
            "Update custom-pkg from source_proj",
            "--description",
            "Automatic update of custom-pkg from source_proj\n\n```diff\nMocked diff output\n```",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
        input=ANY,
    )
