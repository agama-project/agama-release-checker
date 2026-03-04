import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from agama_release_checker.iso_utils import (
    get_packages_from_metadata_file,
    check_command,
    mount_iso,
    unmount_iso,
    get_metadata_path,
    get_packages_from_metadata,
)
from agama_release_checker.models import BinaryPackage

FIXTURES_DIR = Path(__file__).parent / "fixtures"

EXPECTED_PACKAGES = [
    BinaryPackage(
        name="adwaita-icon-theme", version="49.0", release="1.1", arch="noarch"
    ),
    BinaryPackage(
        name="agama", version="19.pre+1452.65cb39696", release="67.1", arch="x86_64"
    ),
    BinaryPackage(
        name="agama-autoinstall",
        version="19.pre+1452.65cb39696",
        release="67.1",
        arch="x86_64",
    ),
    BinaryPackage(
        name="agama-cli", version="19.pre+1452.65cb39696", release="67.1", arch="x86_64"
    ),
    BinaryPackage(
        name="agama-cli-bash-completion",
        version="19.pre+1452.65cb39696",
        release="67.1",
        arch="noarch",
    ),
    BinaryPackage(
        name="agama-common",
        version="19.pre+1452.65cb39696",
        release="67.1",
        arch="x86_64",
    ),
]


def test_get_packages_from_metadata_file_plain():
    """
    Tests that get_packages_from_metadata_file correctly parses a plain JSON file.
    """
    fixture_path = FIXTURES_DIR / "packages.json"
    found_packages = get_packages_from_metadata_file(fixture_path)
    assert found_packages[: len(EXPECTED_PACKAGES)] == EXPECTED_PACKAGES


def test_get_packages_from_metadata_file_gzipped():
    """
    Tests that get_packages_from_metadata_file correctly parses a gzipped JSON file.
    """
    fixture_path = FIXTURES_DIR / "packages.json.gz"
    found_packages = get_packages_from_metadata_file(fixture_path)
    assert found_packages[: len(EXPECTED_PACKAGES)] == EXPECTED_PACKAGES


def test_check_command():
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/ls"
        assert check_command("ls") is True
        mock_which.return_value = None
        assert check_command("nonexistent") is False


def test_mount_iso(tmp_path):
    iso_path = tmp_path / "test.iso"
    mount_point = tmp_path / "mount"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert mount_iso(iso_path, mount_point) is True
        mock_run.assert_called_once()


def test_unmount_iso(tmp_path):
    mount_point = tmp_path / "mount"
    mount_point.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert unmount_iso(mount_point) is True
        mock_run.assert_called_once()
        assert not mount_point.exists()


def test_get_metadata_path(tmp_path):
    mount_point = tmp_path / "mount"
    liveos_dir = mount_point / "LiveOS"
    liveos_dir.mkdir(parents=True)

    # Gzipped exists
    gz_path = liveos_dir / ".packages.json.gz"
    gz_path.touch()
    assert get_metadata_path(mount_point) == gz_path

    # Only plain exists
    gz_path.unlink()
    plain_path = liveos_dir / ".packages.json"
    plain_path.touch()
    assert get_metadata_path(mount_point) == plain_path

    # None exists
    plain_path.unlink()
    assert get_metadata_path(mount_point) is None


def test_get_packages_from_metadata(tmp_path):
    mount_point = tmp_path / "mount"
    liveos_dir = mount_point / "LiveOS"
    liveos_dir.mkdir(parents=True)
    plain_path = liveos_dir / ".packages.json"
    plain_path.write_text("[]")

    with patch(
        "agama_release_checker.iso_utils.get_packages_from_metadata_file"
    ) as mock_get:
        mock_get.return_value = []
        packages = get_packages_from_metadata(mount_point)
        assert packages == []
        mock_get.assert_called_once_with(plain_path)


def test_get_packages_from_metadata_none_found(tmp_path):
    mount_point = tmp_path / "mount"
    (mount_point / "LiveOS").mkdir(parents=True)
    assert get_packages_from_metadata(mount_point) == []
