import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # type: ignore

from agama_release_checker.models import ObsConfig
from agama_release_checker.reports.obs_packages_report import ObsPackagesReport

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename):
    with open(FIXTURES_DIR / filename, "r") as f:
        return f.read()


@patch("agama_release_checker.reports.obs_packages_report.run_cached_command")
def test_packages_in_obs_report(mock_run_cached):
    # Setup mock responses
    def side_effect(cmd, **kwargs):
        args = cmd
        if args == ["osc", "version"]:
            return True, "osc 0.180.0"
        elif args == ["osc", "ls", "systemsmanagement:Agama:Devel"]:
            return True, load_fixture("osc_ls_project.txt")
        elif args == ["osc", "ls", "systemsmanagement:Agama:Devel", "agama"]:
            return True, load_fixture("osc_ls_package_agama.txt")
        elif args == [
            "osc",
            "cat",
            "systemsmanagement:Agama:Devel",
            "agama",
            "agama.obsinfo",
        ]:
            return True, load_fixture("osc_cat_agama_obsinfo.txt")
        elif args == [
            "osc",
            "cat",
            "systemsmanagement:Agama:Devel",
            "agama",
            "agama.spec",
        ]:
            return True, load_fixture("osc_cat_agama_spec.txt")
        elif args == [
            "osc",
            "ls",
            "systemsmanagement:Agama:Devel",
            "rubygem-agama-yast",
        ]:
            return True, load_fixture("osc_ls_package_rubygem_agama_yast.txt")
        elif args == [
            "osc",
            "cat",
            "systemsmanagement:Agama:Devel",
            "rubygem-agama-yast",
            "rubygem-agama-yast.spec",
        ]:
            return True, load_fixture("osc_cat_rubygem_agama_yast_spec.txt")
        elif args == [
            "osc",
            "cat",
            "systemsmanagement:Agama:Devel",
            "rubygem-agama-yast",
            "agama-yast.spec",
        ]:
            return True, load_fixture("osc_cat_agama_yast_spec.txt")
        else:
            return False, ""

    mock_run_cached.side_effect = side_effect

    config = ObsConfig(
        type="obs",
        url="https://build.opensuse.org/project/show/systemsmanagement:Agama:Devel",
        name="obs-sm-A-Devel",
    )

    binary_patterns_by_source = {
        "agama": ["agama"],
        "rubygem-agama-yast": ["rubygem-agama-yast", "agama-yast"],
    }

    spec_names_by_package = {"rubygem-agama-yast": ["rubygem-agama-yast", "agama-yast"]}

    report = ObsPackagesReport(config, binary_patterns_by_source, spec_names_by_package)
    latest_url, packages = report.run()

    assert latest_url is None
    assert packages is not None
    assert len(packages) == 3  # agama, rubygem-agama-yast, agama-yast

    pkg_map = {p.name: p for p in packages}

    # Check agama (dynamic version from .obsinfo)
    assert "agama" in pkg_map
    assert pkg_map["agama"].version == "19.pre+1558.7e90c6ef1"

    # Check rubygem-agama-yast (from spec)
    assert "rubygem-agama-yast" in pkg_map
    assert pkg_map["rubygem-agama-yast"].version == "19.pre.devel1558.7e90c6ef1"

    # Check agama-yast (from spec)
    assert "agama-yast" in pkg_map
    assert pkg_map["agama-yast"].version == "19.pre.devel1558.7e90c6ef1"


@patch("agama_release_checker.reports.obs_packages_report.run_cached_command")
def test_osc_missing(mock_run_cached):
    # Simulate run_cached_command returning failure (e.g. osc not found)
    mock_run_cached.return_value = (False, "")

    config = ObsConfig(
        type="obs", url="https://build.opensuse.org/project/show/foo", name="foo"
    )
    report = ObsPackagesReport(config, {}, {})
    latest_url, packages = report.run()

    assert packages is None
