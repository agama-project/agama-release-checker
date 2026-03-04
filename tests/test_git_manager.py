import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from agama_release_checker.git_manager import GitManager


def test_git_manager_update_repo_clone(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"

    with (
        patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        manager = GitManager(repo_url, repo_name)
        mock_run.return_value = MagicMock(returncode=0)

        manager.update_repo()

        # Should call git clone
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0][0:2] == ["git", "clone"]
        assert repo_url in clone_call[0][0]


def test_git_manager_update_repo_fetch(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"
    repo_path = tmp_path / "git" / repo_name
    repo_path.mkdir(parents=True)

    with (
        patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        manager = GitManager(repo_url, repo_name)
        mock_run.return_value = MagicMock(returncode=0)

        manager.update_repo()

        # Should call git config and git fetch
        calls = [call[0][0] for call in mock_run.call_args_list]
        assert any("config" in cmd for cmd in calls)
        assert any("fetch" in cmd for cmd in calls)


def test_git_manager_get_commit_info(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"
    repo_path = tmp_path / "git" / repo_name
    repo_path.mkdir(parents=True)

    with (
        patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        manager = GitManager(repo_url, repo_name)

        # Mock git show output
        mock_show = MagicMock()
        mock_show.stdout = "2024-03-04 10:00:00 +0100\n"

        # Mock git describe output
        mock_describe = MagicMock()
        mock_describe.stdout = "v1.0-1-gabcdef\n"

        mock_run.side_effect = [mock_show, mock_describe]

        ts, desc = manager.get_commit_info("abcdef")

        assert ts == "2024-03-04 10:00:00 +0100"
        assert desc == "v1.0-1-gabcdef"


def test_git_manager_get_commit_info_missing_repo(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"
    # Repo path does not exist

    with patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path):
        manager = GitManager(repo_url, repo_name)
        ts, desc = manager.get_commit_info("abcdef")
        assert ts is None
        assert desc is None


def test_git_manager_get_commit_info_command_fails(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"
    repo_path = tmp_path / "git" / repo_name
    repo_path.mkdir(parents=True)

    with (
        patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        manager = GitManager(repo_url, repo_name)
        # git show fails, then git describe fails
        err_show = subprocess.CalledProcessError(1, ["git", "show"])
        err_show.stderr = "fatal: bad object abcdef\n"
        err_describe = subprocess.CalledProcessError(1, ["git", "describe"])
        err_describe.stderr = "fatal: Not a valid object name abcdef\n"

        mock_run.side_effect = [err_show, err_describe]
        ts, desc = manager.get_commit_info("abcdef")
        assert ts is None
        assert desc is None


def test_git_manager_get_commit_info_describe_no_tags(tmp_path):
    repo_url = "https://example.com/repo.git"
    repo_name = "test-repo"
    repo_path = tmp_path / "git" / repo_name
    repo_path.mkdir(parents=True)

    with (
        patch("agama_release_checker.git_manager.CACHE_DIR", tmp_path),
        patch("subprocess.run") as mock_run,
    ):
        manager = GitManager(repo_url, repo_name)

        # Mock git show success
        mock_show = MagicMock()
        mock_show.stdout = "2024-03-04 10:00:00 +0100\n"

        # Mock git describe failure with "No names found"
        mock_describe_err = subprocess.CalledProcessError(1, ["git", "describe"])
        mock_describe_err.stderr = "fatal: No names found, cannot describe anything.\n"

        mock_run.side_effect = [mock_show, mock_describe_err]

        ts, desc = manager.get_commit_info("abcdef")

        assert ts == "2024-03-04 10:00:00 +0100"
        assert desc == "(no tags)"
