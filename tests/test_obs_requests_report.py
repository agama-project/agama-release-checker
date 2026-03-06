import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

from agama_release_checker.reports.obs_requests_report import ObsRequestsReport
from agama_release_checker.models import ObsConfig, ObsRequest
from agama_release_checker.reporting import LinkManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename):
    with open(FIXTURES_DIR / filename, "r") as f:
        return f.read()


@patch("agama_release_checker.reports.obs_requests_report.run_cached_command")
def test_obs_submit_requests_report(mock_run_cached):
    # Setup mock responses
    def side_effect(cmd, **kwargs):
        if cmd == ["osc", "version"]:
            return True, "osc 0.180.0"
        elif cmd[0:2] == ["osc", "api"]:
            # Extract package from query
            query = cmd[2]
            if "target/@package='agama'" in query:
                return True, load_fixture("osc_api_search_request_agama.xml")
            else:
                return True, '<collection matches="0"></collection>'
        return False, ""

    mock_run_cached.side_effect = side_effect

    config = ObsConfig(
        url="https://build.opensuse.org/project/show/openSUSE:Factory",
        name="obs-factory",
        submit_requests=True,
    )

    binary_patterns_by_source = {
        "agama": ["agama"],
        "agama-web-ui": ["agama-web-ui"],
    }

    report = ObsRequestsReport(config, binary_patterns_by_source)
    _, requests = report.run()

    assert requests is not None
    assert len(requests) == 1
    req = requests[0]
    assert req.id == "1302942"
    assert req.state == "declined"
    assert req.source_project == "systemsmanagement:Agama:Devel"
    assert req.source_package == "agama"
    assert req.target_project == "openSUSE:Factory"
    assert req.target_package == "agama"
    assert "Current development branch of agama" in req.description
    assert req.created_at == "2025-09-05T14:53:29Z"
    # updated_at corresponds to 'when' attribute in the state element
    assert req.updated_at == "2025-09-05T14:55:46Z"


def test_obs_requests_report_sorting(capsys):
    req1 = ObsRequest(
        id="1",
        state="new",
        source_project="sp",
        source_package="spkg",
        target_project="tp",
        target_package="tpkg",
        created_at="2024-01-01T10:00:00Z",
        updated_at="2024-01-01T10:00:00Z",
        description="old",
    )
    req2 = ObsRequest(
        id="2",
        state="new",
        source_project="sp",
        source_package="spkg",
        target_project="tp",
        target_package="tpkg",
        created_at="2024-02-01T10:00:00Z",
        updated_at="2024-02-01T10:00:00Z",
        description="new",
    )

    config = ObsConfig(url="http://obs/", name="obs")
    lm = LinkManager([])
    report = ObsRequestsReport(config, {})
    # render sorts by the first column (Updated) descending
    report.render([req1, req2], lm)

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if "|" in line]
    # Header, separator, then rows
    # Sorting: newest first (2024-02-01)
    assert "2024-02-01" in lines[2]
    assert "2024-01-01" in lines[3]
    # Check that ID is formatted as a reference link
    assert "[2][]" in lines[2]
    assert "[1][]" in lines[3]
    # Check that 'Created' is NOT in the header
    assert "Created" not in lines[0]
