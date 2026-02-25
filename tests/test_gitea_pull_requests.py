import json
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any

from agama_release_checker.reports.gitea_pull_requests import GiteaRequestsReport
from agama_release_checker.models import GiteaConfig, GiteaPullRequest


@patch("agama_release_checker.reports.gitea_pull_requests.run_cached_command")
def test_gitea_pull_requests_report(mock_run):
    # Mock data from tea
    tea_output = [
        {
            "index": "14",
            "state": "open",
            "author": "Imobach Gonzalez Sosa",
            "url": "https://src.suse.de/pool/rubygem-agama-yast/pulls/14",
            "title": "Update translations",
            "mergeable": "true",
            "base": "slfo-1.2",
            "created": "2026-02-02T07:17:32Z",
            "updated": "2026-02-03T09:27:06Z",
            "comments": "4",
        }
    ]

    mock_run.return_value = (True, json.dumps(tea_output))

    config = GiteaConfig(
        type="gitea",
        url="https://src.suse.de/pool/",
        name="ibs-pool-slfo1.2",
        branch="slfo-1.2",
    )
    binary_patterns_by_source = {
        "rubygem-agama-yast": ["rubygem-agama-yast"],
    }

    report = GiteaRequestsReport(config, binary_patterns_by_source)
    _, prs = report.run()

    assert len(prs) == 1
    assert prs[0].index == "14"
    assert prs[0].title == "Update translations"
    assert prs[0].mergeable is True
    assert prs[0].base == "slfo-1.2"

    # Verify tea command was called with correct arguments
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    cmd = args[0]
    assert "tea" in cmd
    assert "--login" in cmd
    assert "src.suse.de" in cmd
    assert "--repo" in cmd
    assert "pool/rubygem-agama-yast" in cmd
    assert kwargs["cache_dir"] is not None


@patch("agama_release_checker.reports.gitea_pull_requests.run_cached_command")
def test_gitea_pull_requests_report_branch_filtering(mock_run):
    # Mock data from tea with different base branches
    tea_output = [
        {
            "index": "14",
            "base": "slfo-1.2",
            "title": "PR for 1.2",
        },
        {
            "index": "15",
            "base": "slfo-main",
            "title": "PR for main",
        },
    ]

    mock_run.return_value = (True, json.dumps(tea_output))

    config = GiteaConfig(
        type="gitea",
        url="https://src.suse.de/pool/",
        name="ibs-pool-slfo1.2",
        branch="slfo-1.2",
    )
    binary_patterns_by_source = {
        "agama": ["agama"],
    }

    report = GiteaRequestsReport(config, binary_patterns_by_source)
    _, prs = report.run()

    # Should only have one PR because of branch filtering
    assert len(prs) == 1
    assert prs[0].index == "14"
    assert prs[0].title == "PR for 1.2"
