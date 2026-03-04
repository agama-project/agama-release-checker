from agama_release_checker.reporting import (
    LinkManager,
    print_packages_table,
    get_git_timestamps,
)
from agama_release_checker.models import (
    GitConfig,
    BinaryPackage,
    GitTimestamp,
    GitRevisionTimestamps,
)
from unittest.mock import patch


def test_link_manager_format_version():
    git_configs = [
        GitConfig(name="agama", url="https://github.com/agama-project/agama/")
    ]
    lm = LinkManager(git_configs)

    # Version with hash
    v = lm.format_version("agama", "19.pre+1690.a6a0f3735")
    assert v == "19.pre+1690.[a6a0f3735][]"
    assert "a6a0f3735" in lm.links

    # Version without hash
    v2 = lm.format_version("agama", "1.0")
    assert v2 == "1.0"

    # Fallback logic for agama
    v3 = lm.format_version("agama-web-ui", "1.0.abcdef123")
    assert v3 == "1.0.[abcdef123][]"
    assert "abcdef123" in lm.links


def test_print_packages_table_with_links(capsys):
    git_configs = [
        GitConfig(name="agama", url="https://github.com/agama-project/agama/")
    ]
    lm = LinkManager(git_configs)
    all_found = {
        "agama": [
            BinaryPackage(
                name="agama", version="1.0.a6a0f3735", release="1", arch="x86_64"
            )
        ]
    }

    print_packages_table(all_found, "TEST", link_manager=lm)
    captured = capsys.readouterr()
    assert "1.0.[a6a0f3735][]" in captured.out
    assert "Git Updated" in captured.out


@patch("agama_release_checker.reporting.GitManager")
def test_get_git_timestamps_with_links(mock_git_manager):
    git_hashes = {"agama": {"abcdef1"}}
    git_configs = [GitConfig(url="https://github.com/a/b/", name="agama")]
    lm = LinkManager(git_configs)

    mock_instance = mock_git_manager.return_value
    mock_instance.get_commit_info.return_value = (
        "2024-03-04 10:00:00 +0100",
        "Commit abcdef1 message",
    )

    with patch(
        "agama_release_checker.reporting.format_timestamp",
        return_value="2024-03-04 10:00",
    ):
        timestamps = get_git_timestamps(git_hashes, git_configs, link_manager=lm)

    assert timestamps == GitRevisionTimestamps(
        {"abcdef1": GitTimestamp("2024-03-04 10:00")}
    )


def test_link_manager_print_definitions(capsys):
    git_configs = [
        GitConfig(name="agama", url="https://github.com/agama-project/agama/")
    ]
    lm = LinkManager(git_configs)
    lm.register_hash("agama", "a6a0f3735")

    lm.print_definitions()
    captured = capsys.readouterr()
    assert (
        "[a6a0f3735]: https://github.com/agama-project/agama/commit/a6a0f3735"
        in captured.out
    )
