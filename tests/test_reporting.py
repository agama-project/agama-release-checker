from unittest.mock import patch, MagicMock
from agama_release_checker.reporting import (
    print_markdown_table,
    extract_git_hashes,
    print_git_report,
    LinkManager,
)
from agama_release_checker.models import (
    BinaryPackage,
    SourcePackage,
    GitConfig,
)


def test_print_markdown_table(capsys):
    headers = ["Country", "Home computer"]
    rows = [
        ["UK", "ZX Spectrum"],
        ["CS", "Didaktik Gama"],
    ]

    print_markdown_table(headers, rows)

    captured = capsys.readouterr()
    expected_output = (
        "| Country | Home computer |\n"
        "|---------|---------------|\n"
        "| UK      | ZX Spectrum   |\n"
        "| CS      | Didaktik Gama |\n"
    )
    assert captured.out == expected_output


def test_print_markdown_table_empty(capsys):
    print_markdown_table([], [["row"]])
    captured = capsys.readouterr()
    assert captured.out == ""


def test_print_markdown_table_extra_columns(capsys):
    headers = ["Col1"]
    rows = [["Val1", "Val2"]]  # Extra column Val2
    print_markdown_table(headers, rows)
    captured = capsys.readouterr()
    # It should not crash and just print the first column
    assert "| Col1 |\n|------|\n| Val1 |" in captured.out


def test_extract_git_hashes():
    packages = [
        BinaryPackage(
            name="agama", version="1.0+git.abcdef1", release="1", arch="x86_64"
        ),
        BinaryPackage(
            name="agama-cli", version="1.0+git.abcdef2", release="1", arch="x86_64"
        ),
        SourcePackage(name="web-ui", version="2.0", release="1"),
    ]
    binary_patterns_by_source = {
        "agama": ["agama", "agama-cli"],
        "web-ui": ["web-ui"],
    }
    hashes = extract_git_hashes(packages, binary_patterns_by_source)
    assert "agama" in hashes
    assert hashes["agama"] == {"abcdef1", "abcdef2"}
    assert "web-ui" not in hashes


@patch("agama_release_checker.reporting.GitManager")
def test_print_git_report(mock_git_manager, capsys):
    git_hashes = {
        "agama-web-ui": {"abcdef1"},  # Tests fallback to "agama"
        "agama": {"abcdef2"},  # Same repo "agama", tests existing key in hashes_by_repo
        "unknown-pkg": {"1234567"},  # Tests "No git config found" debug log
    }
    git_configs = [GitConfig(url="https://github.com/a/b/", name="agama")]

    mock_manager_instance = mock_git_manager.return_value
    mock_manager_instance.get_commit_info.return_value = (
        "2024-03-04 10:00:00 +0100",
        "Commit message",
    )

    with patch("agama_release_checker.reporting.format_timestamp") as mock_fmt:
        mock_fmt.return_value = "2024-03-04 10:00"
        with patch("agama_release_checker.reporting.logging") as mock_logging:
            print_git_report(git_hashes, git_configs, LinkManager(git_configs))
            mock_logging.debug.assert_any_call(
                "No git config found for package unknown-pkg"
            )

    captured = capsys.readouterr()
    assert "## Git Commits" in captured.out
    assert "### Repo: agama" in captured.out
    assert "| 2024-03-04 10:00 | Commit message ([abcdef1][]) |" in captured.out
    assert "| 2024-03-04 10:00 | Commit message ([abcdef2][]) |" in captured.out
    assert "https://github.com/a/b/commit/abcdef1" not in captured.out


def test_print_git_report_empty(capsys):
    print_git_report({}, [], LinkManager([]))
    captured = capsys.readouterr()
    assert captured.out == ""


@patch("agama_release_checker.reporting.logging")
def test_print_git_report_no_configs(mock_logging, capsys):
    print_git_report({"agama": {"abcdef1"}}, [], LinkManager([]))
    mock_logging.warning.assert_called_once()
    captured = capsys.readouterr()
    assert "## Git Commits" not in captured.out
