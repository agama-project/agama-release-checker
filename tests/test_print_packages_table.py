from agama_release_checker.reporting import print_packages_table, LinkManager
from agama_release_checker.models import (
    BinaryPackage,
    SourcePackage,
    GitTimestamp,
    GitRevisionTimestamps,
)


def test_print_packages_table_empty(capsys):
    print_packages_table({}, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "  (No matching packages found in TEST)" in captured.out


def test_print_packages_table_consistent(capsys):
    all_found = {
        "agama": [
            BinaryPackage(name="agama", version="1.0", release="1", arch="x86_64"),
            BinaryPackage(name="agama-cli", version="1.0", release="1", arch="x86_64"),
        ]
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "| Git Updated | Source Name | Version | Release |" in captured.out
    assert "| Unknown     | agama       | 1.0     | 1       |" in captured.out
    assert ".../!" not in captured.out


def test_print_packages_table_inconsistent_version(capsys):
    all_found = {
        "agama": [
            SourcePackage(name="agama", version="1.0", release="1"),
            SourcePackage(name="agama", version="1.1", release="1"),
        ]
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert r"| Unknown     | agama       | 1.0     | 1.../!\ |" in captured.out


def test_print_packages_table_inconsistent_release(capsys):
    all_found = {
        "agama": [
            SourcePackage(name="agama", version="1.0", release="1"),
            SourcePackage(name="agama", version="1.0", release="2"),
        ]
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert r"| Unknown     | agama       | 1.0     | 1.../!\ |" in captured.out


def test_print_packages_table_multiple_sources(capsys):
    all_found = {
        "agama": [SourcePackage(name="agama", version="1.0", release="1")],
        "web-ui": [SourcePackage(name="web-ui", version="2.0", release="1")],
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "| Unknown     | agama       | 1.0     | 1       |" in captured.out
    assert "| Unknown     | web-ui      | 2.0     | 1       |" in captured.out


def test_print_packages_table_skip_empty_found(capsys):
    all_found = {
        "agama": [],  # Should be skipped
        "web-ui": [SourcePackage(name="web-ui", version="2.0", release="1")],
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "agama" not in captured.out
    assert "web-ui" in captured.out


def test_print_packages_table_sorting(capsys):
    all_found = {
        "older": [SourcePackage(name="older", version="1.0.abc1111", release="1")],
        "newer": [SourcePackage(name="newer", version="1.1.abc2222", release="1")],
        "unknown": [SourcePackage(name="unknown", version="1.2", release="1")],
    }
    timestamps = GitRevisionTimestamps(
        {
            "abc1111": GitTimestamp("2024-01-01"),
            "abc2222": GitTimestamp("2024-02-01"),
        }
    )
    print_packages_table(all_found, "TEST", LinkManager([]), timestamps=timestamps)
    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if "|" in line]
    # Header, separator, then rows
    # Sorting: newest first (2024-02-01), then older (2024-01-01), then Unknown (0000-00-00 logic)
    assert "2024-02-01" in lines[2]
    assert "newer" in lines[2]
    assert "2024-01-01" in lines[3]
    assert "older" in lines[3]
    assert "Unknown" in lines[4]
    assert "unknown" in lines[4]
