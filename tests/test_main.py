import argparse
import logging
import sys
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from agama_release_checker.main import main
from agama_release_checker.models import (
    AppConfig,
    MirrorcacheConfig,
    BinaryPackage,
)


def test_main_basic_execution(tmp_path):
    # Mock CLI arguments
    mock_args = MagicMock()
    mock_args.verbose = False
    mock_args.repo = None
    mock_args.no_command_cache = False
    mock_args.recent_rq = False
    mock_args.internal = False
    mock_args.output = str(tmp_path / "test-report.md")
    mock_args.timezone = "Europe/Berlin"

    # Mock AppConfig
    mock_repo = MirrorcacheConfig(
        url="http://example.com/", name="test-iso", files=["*.iso"]
    )
    mock_config = MagicMock(spec=AppConfig)
    mock_config.repositories = [mock_repo]
    mock_config.binary_patterns_by_source = {"agama": ["agama"]}
    mock_config.git_configs = []

    # Mock ISO report
    mock_iso_report_instance = MagicMock()
    mock_iso_report_instance.run.return_value = ("http://example.com/test.iso", [])

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch(
            "agama_release_checker.main.AppConfig.from_file", return_value=mock_config
        ),
        patch("agama_release_checker.main.check_command", return_value=True),
        patch(
            "agama_release_checker.main.IsoPackagesReport",
            return_value=mock_iso_report_instance,
        ),
        patch("agama_release_checker.main.get_git_timestamps") as mock_git_report,
        patch("builtins.open", mock_open()),
    ):
        main()

        mock_iso_report_instance.run.assert_called_once()
        mock_iso_report_instance.render.assert_called_once()
        mock_git_report.assert_called_once()


def test_main_with_all_report_types(tmp_path):
    from agama_release_checker.models import ObsConfig, GiteaConfig

    mock_args = MagicMock()
    mock_args.verbose = True
    mock_args.repo = None
    mock_args.no_command_cache = False
    mock_args.recent_rq = True
    mock_args.internal = True
    mock_args.output = str(tmp_path / "full-report.md")
    mock_args.timezone = "Europe/Berlin"

    mock_obs = ObsConfig(
        url="http://obs.example.com/", name="test-obs", submit_requests=True
    )
    mock_gitea = GiteaConfig(
        url="http://gitea.example.com/", name="test-gitea", branch="main"
    )

    mock_config = MagicMock(spec=AppConfig)
    mock_config.repositories = [mock_obs, mock_gitea]
    mock_config.binary_patterns_by_source = {"agama": ["agama"]}
    mock_config.git_configs = []
    mock_config.spec_names_by_package = {}

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch(
            "agama_release_checker.main.AppConfig.from_file", return_value=mock_config
        ),
        patch("agama_release_checker.main.check_command", return_value=True),
        patch("agama_release_checker.main.ObsPackagesReport") as mock_obs_pkg,
        patch("agama_release_checker.main.ObsRequestsReport") as mock_obs_req,
        patch("agama_release_checker.main.GiteaPackagesReport") as mock_gitea_pkg,
        patch("agama_release_checker.main.GiteaRequestsReport") as mock_gitea_req,
        patch("agama_release_checker.main.get_git_timestamps"),
        patch("builtins.open", mock_open()),
    ):  # Set up instance mocks
        mock_obs_pkg.return_value.run.return_value = (None, [])
        mock_obs_req.return_value.run.return_value = (None, [])
        mock_gitea_pkg.return_value.run.return_value = (None, [])
        mock_gitea_req.return_value.run.return_value = (None, [])

        main()

        mock_obs_pkg.assert_called_once()
        mock_obs_req.assert_called_once()
        mock_gitea_pkg.assert_called_once()
        mock_gitea_req.assert_called_once()


def test_main_repo_filtering(tmp_path):
    mock_args = MagicMock()
    mock_args.verbose = False
    mock_args.repo = ["selected-repo"]
    mock_args.no_command_cache = False
    mock_args.recent_rq = False
    mock_args.internal = False
    mock_args.output = str(tmp_path / "filtered-report.md")
    mock_args.timezone = "Europe/Berlin"

    repo1 = MirrorcacheConfig(
        url="http://example.com/1", name="selected-repo", files=["*.iso"]
    )
    repo2 = MirrorcacheConfig(
        url="http://example.com/2", name="ignored-repo", files=["*.iso"]
    )

    mock_config = MagicMock(spec=AppConfig)
    mock_config.repositories = [repo1, repo2]
    mock_config.binary_patterns_by_source = {}
    mock_config.git_configs = []

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch(
            "agama_release_checker.main.AppConfig.from_file", return_value=mock_config
        ),
        patch("agama_release_checker.main.check_command", return_value=True),
        patch("agama_release_checker.main.IsoPackagesReport") as mock_iso,
        patch("agama_release_checker.main.get_git_timestamps"),
        patch("builtins.open", mock_open()),
    ):
        mock_iso.return_value.run.return_value = (None, [])
        main()

        # Should only be called for "selected-repo"
        assert mock_iso.call_count == 1
        mock_iso.assert_called_once_with(repo1)


def test_main_invalid_timezone():
    mock_args = MagicMock()
    mock_args.timezone = "Invalid/Timezone"
    mock_args.verbose = False

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch("sys.exit") as mock_exit,
    ):
        main()
        mock_exit.assert_called_once_with(1)


def test_main_missing_commands():
    mock_args = MagicMock()
    mock_args.timezone = "Europe/Berlin"
    mock_args.output = "dummy.md"
    mock_args.verbose = False

    mock_config = MagicMock(spec=AppConfig)
    mock_config.git_configs = []

    with (
        patch("argparse.ArgumentParser.parse_args", return_value=mock_args),
        patch(
            "agama_release_checker.main.AppConfig.from_file", return_value=mock_config
        ),
        patch("agama_release_checker.main.check_command", return_value=False),
        patch("sys.exit") as mock_exit,
        patch("builtins.open", mock_open()),
    ):
        main()
        mock_exit.assert_called_once_with(1)
