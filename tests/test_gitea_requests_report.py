import json
from unittest.mock import MagicMock, patch

from agama_release_checker.reports.gitea_requests_report import GiteaRequestsReport
from agama_release_checker.models import GiteaConfig, GiteaPullRequest


@patch("agama_release_checker.reports.gitea_requests_report.run_cached_command")
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


@patch("agama_release_checker.reports.gitea_requests_report.run_cached_command")
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


def test_gitea_requests_report_sorting(capsys):
    pr1 = GiteaPullRequest(
        index="1",
        state="open",
        author="a1",
        url="http://u1",
        title="t1",
        mergeable=True,
        base="b1",
        created_at="2024-01-01T10:00:00Z",
        updated_at="2024-01-01T10:00:00Z",
        comments="0",
    )
    pr2 = GiteaPullRequest(
        index="2",
        state="open",
        author="a2",
        url="http://u2",
        title="t2",
        mergeable=True,
        base="b1",
        created_at="2024-02-01T10:00:00Z",
        updated_at="2024-02-01T10:00:00Z",
        comments="0",
    )

    config = GiteaConfig(url="http://gitea/", name="gitea")
    report = GiteaRequestsReport(config, {})
    # render sorts by the first column (Updated) descending
    report.render([pr1, pr2])

    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if "|" in line]
    # Header, separator, then rows
    # Sorting: newest first (2024-02-01)
    assert "2024-02-01" in lines[2]
    assert "2024-01-01" in lines[3]
