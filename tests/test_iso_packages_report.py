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
        patch(
            "agama_release_checker.reports.iso_packages_report.is_wwwdirfs_available",
            return_value=False,
        ),
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


import threading
import http.server
import socketserver
import pytest
import tempfile
import time
from agama_release_checker.iso_utils import is_wwwdirfs_available


@pytest.mark.skipif(not is_wwwdirfs_available(), reason="wwwdirfs not available")
def test_iso_packages_report_integration_wwwdirfs(caplog):
    caplog.set_level(logging.DEBUG)

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)

        # Setup paths
        repo_name = "test-repo-wwwdirfs"
        repo_dir = tmp_path / "mirrorcache" / repo_name
        repo_dir.mkdir(parents=True)

        # We will serve the tests/fixtures directory
        fixtures_dir = Path("tests/fixtures")

        iso_name = "agama-installer.x86_64-openSUSE.iso"

        # Create a fake index.html for find_iso_urls to parse
        # find_iso_urls looks for `<a href="...iso">`
        index_path = repo_dir / "index.html"
        index_path.write_text(f'<a href="{iso_name}">{iso_name}</a>')

        # We also need the iso_name to actually "exist" in the served directory
        # so wwwdirfs sees it. We can create a symlink in fixtures to mirrorcache.json
        fake_iso_path = fixtures_dir / iso_name
        if not fake_iso_path.exists():
            fake_iso_path.symlink_to("mirrorcache.json")

        # Set up HTTP server
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(fixtures_dir), **kwargs)

            def log_message(self, format, *args):
                pass  # Suppress logging

            def do_GET(self):
                if "?jsontable" in self.path:
                    json_path = fixtures_dir / "mirrorcache.json"
                    with open(json_path, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    super().do_GET()

            def do_HEAD(self):
                if "?jsontable" in self.path:
                    json_path = fixtures_dir / "mirrorcache.json"
                    content_len = json_path.stat().st_size
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Content-Length", str(content_len))
                    self.end_headers()
                else:
                    super().do_HEAD()

        httpd = socketserver.ThreadingTCPServer(("", 0), Handler)
        port = httpd.server_address[1]

        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        try:
            config = MirrorcacheConfig(
                url=f"http://localhost:{port}/", name=repo_name, files=["*.iso"]
            )

            with (
                patch(
                    "agama_release_checker.reports.iso_packages_report.find_iso_urls"
                ) as mock_find,
                patch(
                    "agama_release_checker.reports.iso_packages_report.CACHE_DIR",
                    tmp_path,
                ),
                patch(
                    "agama_release_checker.reports.iso_packages_report.IsoMounter"
                ) as mock_iso_mounter,
            ):
                mock_find.return_value = [f"http://localhost:{port}/{iso_name}"]

                # Setup the mock context manager to fail
                mock_iso_mounter.return_value.__enter__.side_effect = RuntimeError(
                    "Mocked mount failure"
                )

                report = IsoPackagesReport(config)
                latest_url, packages = report.run()

                assert latest_url == f"http://localhost:{port}/{iso_name}"
                assert packages is None

                # Verify wwwdirfs was attempted
                assert "Mounting WWW directory" in caplog.text
                assert mock_iso_mounter.called

            # Small sleep to ensure unmounts complete before deleting directory
            time.sleep(0.5)

        finally:
            if fake_iso_path.exists():
                fake_iso_path.unlink()

            # Shutdown server AFTER everything is unmounted and tmp_path is deleted
            httpd.shutdown()
            httpd.server_close()
            server_thread.join(timeout=1)
