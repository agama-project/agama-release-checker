import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from agama_release_checker.maker import ReleaseMaker
from agama_release_checker.models import AppConfig


@pytest.fixture
def mock_config():
    config = MagicMock(spec=AppConfig)
    config.obs_packages = ["pkg1", "pkg2"]
    return config


from unittest.mock import patch, MagicMock, ANY


@patch("agama_release_checker.maker.subprocess.run")
def test_submit_to_obs(mock_run, mock_config):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")

    maker = ReleaseMaker(mock_config)
    maker.submit_to_obs("source_proj", "target_proj")

    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["osc", "sr", "source_proj", "pkg1", "target_proj"],
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
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")

    # For git status --porcelain, return some output to trigger commit
    def run_side_effect(cmd, **kwargs):
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="M  file", stderr="")
        return MagicMock(returncode=0, stdout="OK", stderr="")

    mock_run.side_effect = run_side_effect

    # Mock iterdir to avoid FileNotFoundError
    mock_iterdir.return_value = []

    maker = ReleaseMaker(mock_config)
    maker.submit_to_gitea("source_proj", "target_org", "target_branch")

    assert mock_run.call_count >= 8
    mock_run.assert_any_call(
        ["osc", "co", "source_proj", "pkg1"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ANY,
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
