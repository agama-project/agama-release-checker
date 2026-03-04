from agama_release_checker.reporting import print_packages_table, LinkManager
from agama_release_checker.models import BinaryPackage, SourcePackage


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
    assert "| Source Name | Version | Release |" in captured.out
    assert "| agama       | 1.0     | 1       |" in captured.out
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
    assert r"| agama       | 1.0     | 1.../!\ |" in captured.out


def test_print_packages_table_inconsistent_release(capsys):
    all_found = {
        "agama": [
            SourcePackage(name="agama", version="1.0", release="1"),
            SourcePackage(name="agama", version="1.0", release="2"),
        ]
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert r"| agama       | 1.0     | 1.../!\ |" in captured.out


def test_print_packages_table_multiple_sources(capsys):
    all_found = {
        "agama": [SourcePackage(name="agama", version="1.0", release="1")],
        "web-ui": [SourcePackage(name="web-ui", version="2.0", release="1")],
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "| agama       | 1.0     | 1       |" in captured.out
    assert "| web-ui      | 2.0     | 1       |" in captured.out


def test_print_packages_table_skip_empty_found(capsys):
    all_found = {
        "agama": [],  # Should be skipped
        "web-ui": [SourcePackage(name="web-ui", version="2.0", release="1")],
    }
    print_packages_table(all_found, "TEST", LinkManager([]))
    captured = capsys.readouterr()
    assert "agama" not in captured.out
    assert "web-ui" in captured.out
