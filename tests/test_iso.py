import json
from pathlib import Path
from agama_release_checker.iso_utils import get_packages_from_metadata_file
from agama_release_checker.models import Package

FIXTURES_DIR = Path(__file__).parent / "fixtures"

EXPECTED_PACKAGES = [
    Package(name="adwaita-icon-theme", version="49.0", release="1.1", arch="noarch"),
    Package(
        name="agama", version="19.pre+1452.65cb39696", release="67.1", arch="x86_64"
    ),
    Package(
        name="agama-autoinstall",
        version="19.pre+1452.65cb39696",
        release="67.1",
        arch="x86_64",
    ),
    Package(
        name="agama-cli", version="19.pre+1452.65cb39696", release="67.1", arch="x86_64"
    ),
    Package(
        name="agama-cli-bash-completion",
        version="19.pre+1452.65cb39696",
        release="67.1",
        arch="noarch",
    ),
    Package(
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
