import time
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from agama_release_checker.caching import (
    _sanitize_filename,
    _generate_cache_filename,
    run_cached_command,
)


def test_sanitize_filename():
    assert _sanitize_filename("a b/c.d") == "a_b_c.d"
    assert _sanitize_filename("osc-api?match=foo") == "osc-api_match_foo"


def test_generate_cache_filename():
    cmd = ["osc", "api", "/search/request?match=foo"]
    filename = _generate_cache_filename(cmd)
    assert filename == "osc_api__search_request_match_foo.txt"


def test_run_cached_command_cache_hit(tmp_path):
    cmd = ["echo", "hello"]
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / _generate_cache_filename(cmd)
    cache_file.write_text("cached output")

    # Mock time to ensure cache is not stale
    with patch("time.time", return_value=cache_file.stat().st_mtime + 10):
        success, output = run_cached_command(cmd, cache_dir=cache_dir)

    assert success is True
    assert output == "cached output"


def test_run_cached_command_cache_miss(tmp_path):
    cmd = ["echo", "world"]
    cache_dir = tmp_path / "cache"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="world\n", returncode=0)
        success, output = run_cached_command(cmd, cache_dir=cache_dir)

    assert success is True
    assert output == "world\n"
    cache_file = cache_dir / _generate_cache_filename(cmd)
    assert cache_file.exists()
    assert cache_file.read_text() == "world\n"


def test_run_cached_command_stale_cache(tmp_path):
    cmd = ["date"]
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / _generate_cache_filename(cmd)
    cache_file.write_text("old date")

    # Mock time to make cache stale (max_age is 3600)
    with patch("time.time", return_value=cache_file.stat().st_mtime + 4000):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="new date\n", returncode=0)
            success, output = run_cached_command(cmd, cache_dir=cache_dir)

    assert success is True
    assert output == "new date\n"
    assert cache_file.read_text() == "new date\n"


def test_run_cached_command_force_refresh(tmp_path):
    cmd = ["whoami"]
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / _generate_cache_filename(cmd)
    cache_file.write_text("someone")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="me\n", returncode=0)
        success, output = run_cached_command(
            cmd, cache_dir=cache_dir, force_refresh=True
        )

    assert success is True
    assert output == "me\n"
    assert cache_file.read_text() == "me\n"


def test_run_cached_command_no_cache():
    cmd = ["uptime"]
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="up 1 day\n", returncode=0)
        success, output = run_cached_command(cmd, cache_dir=None)

    assert success is True
    assert output == "up 1 day\n"


def test_run_cached_command_failure(tmp_path):
    cmd = ["false"]
    cache_dir = tmp_path / "cache"

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, cmd)
        success, output = run_cached_command(cmd, cache_dir=cache_dir)

    assert success is False
    assert output == ""
    # Should not create a cache file for failures
    assert not any(cache_dir.iterdir()) if cache_dir.exists() else True


def test_run_cached_command_not_found(tmp_path):
    cmd = ["nonexistent_cmd"]
    cache_dir = tmp_path / "cache"

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()
        success, output = run_cached_command(cmd, cache_dir=cache_dir)

    assert success is False
    assert output == ""
