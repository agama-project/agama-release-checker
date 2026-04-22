import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil
import os
import time

from agama_release_checker.reports.iso_packages_report import IsoPackagesReport
from agama_release_checker.models import MirrorcacheConfig, BinaryPackage


def test_iso_packages_report_caching(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)

    # Setup paths
    repo_name = "test-repo"
    repo_dir = tmp_path / "mirrorcache" / repo_name
    repo_dir.mkdir(parents=True)

    iso_name = "test.iso"
    iso_path = repo_dir / iso_name
    iso_path.touch()

    # Metadata cache file
    metadata_cache_path = iso_path.with_suffix(".packages.json")

    # Mock config
    config = MirrorcacheConfig(
        url="http://example.com/iso/", name=repo_name, files=["*.iso"]
    )

    # Mock dependencies
    with (
        patch(
            "agama_release_checker.reports.iso_packages_report.find_iso_urls"
        ) as mock_find,
        patch(
            "agama_release_checker.reports.iso_packages_report.download_file"
        ) as mock_download,
        patch("agama_release_checker.iso_utils.mount_iso") as mock_mount,
        patch("agama_release_checker.iso_utils.unmount_iso") as mock_unmount,
        patch(
            "agama_release_checker.reports.iso_packages_report.get_metadata_path"
        ) as mock_get_meta_path,
        patch(
            "agama_release_checker.reports.iso_packages_report.get_packages_from_metadata_file"
        ) as mock_get_pkgs,
        patch("agama_release_checker.reports.iso_packages_report.CACHE_DIR", tmp_path),
    ):

        mock_find.return_value = ["http://example.com/iso/test.iso"]
        mock_get_meta_path.return_value = Path("/mock/mount/LiveOS/.packages.json")
        mock_mount.return_value = True

        # Fake package data
        mock_get_pkgs.return_value = [
            BinaryPackage(name="pkg1", version="1.0", release="1", arch="x86_64")
        ]

        report = IsoPackagesReport(config)

        # First run: should mount and cache
        with patch("shutil.copy") as mock_copy:
            latest_url, packages = report.run()

            assert latest_url == "http://example.com/iso/test.iso"
            assert len(packages) == 1
            mock_mount.assert_called_once()
            mock_copy.assert_called_once()
            assert "Caching metadata from ISO" in caplog.text

        caplog.clear()

        # Second run: metadata exists, should skip mounting
        metadata_cache_path.touch()
        latest_url, packages = report.run()

        assert len(packages) == 1
        # mount_iso should NOT be called again if cached
        assert mock_mount.call_count == 1
        assert "In cache" in caplog.text


def test_iso_packages_report_cleanup(tmp_path):
    repo_name = "test-repo"
    repo_dir = tmp_path / "mirrorcache" / repo_name
    repo_dir.mkdir(parents=True)

    # Create 4 old ISOs and their metadata
    for i in range(4):
        iso = repo_dir / f"test-{i}.iso"
        iso.touch()
        iso.with_suffix(".packages.json.gz").touch()
        # Set different mtimes
        os.utime(iso, (time.time() - (10 - i) * 100, time.time() - (10 - i) * 100))

    config = MirrorcacheConfig(
        url="http://example.com/", name=repo_name, files=["*.iso"]
    )
    report = IsoPackagesReport(config)

    # We only keep 3
    report._cleanup_old_isos(repo_dir, keep=3)

    remaining_isos = list(repo_dir.glob("*.iso"))
    assert len(remaining_isos) == 3

    # Check that metadata for deleted ISO is also gone
    remaining_metadata = list(repo_dir.glob("*.packages.json.gz"))
    assert len(remaining_metadata) == 3
