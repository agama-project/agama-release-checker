import pytest
import json
from unittest.mock import patch, MagicMock, ANY
from agama_release_checker.maker import ReleaseMaker
from agama_release_checker.models import AppConfig


@pytest.fixture
def mock_config():
    """Provides a mock AppConfig with test packages."""
    config = MagicMock(spec=AppConfig)
    config.obs_packages = ["pkg1", "pkg2"]
    return config


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs(mock_run, mock_config):
    """Verifies that submit_to_obs calls osc sr with the correct arguments."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")

    maker = ReleaseMaker(mock_config)
    maker.submit_to_obs("source_proj", "target_proj")

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        [
            "osc",
            "sr",
            "--yes",
            "-m",
            "Automatic update from source_proj",
            "source_proj",
            "pkg1",
            "target_proj",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
    )


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
        if "pr" in cmd and "list" in cmd:
            # Return empty list to trigger PR creation
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    # Mock iterdir to avoid FileNotFoundError
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea("source_proj", "target_org", "target_branch")

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
    )
    mock_run.assert_any_call(
        ["git", "clone", "gitea@src.suse.de:target_org/pkg1.git", ANY],
        check=True,
        capture_output=True,
        text=True,
        cwd=None,
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
            "target_branch-update",
            "--title",
            "Update from OBS source_proj",
            "--description",
            "Automatic update from source_proj",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
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
                            "head": "target_branch-update",
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
    maker.submit_to_gitea("source_proj", "target_org", "target_branch")

    # Verify that tea pr create was NOT called
    for call in mock_run.call_args_list:
        args = call[0][0]
        assert not (args[0] == "tea" and args[2] == "create")
