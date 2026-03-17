import json
from pathlib import Path
import time
import pytest  # type: ignore
import requests_mock  # type: ignore
from agama_release_checker.network import find_iso_urls

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_find_iso_urls(requests_mock):
    """
    Tests that find_iso_urls correctly parses and filters ISO URLs from a JSON response.
    """
    base_url = "http://example.com/iso_dir/"
    json_url = base_url + "?jsontable"
    fixture_path = FIXTURES_DIR / "mirrorcache.json"
    with open(fixture_path, "r") as f:
        json_content = f.read()

    requests_mock.get(json_url, text=json_content)

    patterns = ["*.aarch64*.iso", "*.x86_64*.iso"]
    expected_urls = [
        "http://example.com/iso_dir/agama-installer.aarch64-19.pre.0.0-openSUSE-Build16.23.iso",
        "http://example.com/iso_dir/agama-installer.aarch64-openSUSE.iso",
        "http://example.com/iso_dir/agama-installer.x86_64-19.pre.0.0-openSUSE-Build16.23.iso",
        "http://example.com/iso_dir/agama-installer.x86_64-openSUSE.iso",
    ]

    found_urls = find_iso_urls(base_url, patterns)

    assert sorted(found_urls) == sorted(expected_urls)


def test_find_iso_urls_caching(requests_mock, tmp_path):
    """Tests the caching mechanism of find_iso_urls."""
    base_url = "http://example.com/iso_dir/"
    json_url = base_url + "?jsontable"
    cache_file = tmp_path / "index.json"
    patterns = ["*.iso"]

    # 1. First call: Should fetch and write to cache
    mock_response_1 = json.dumps({"data": [{"name": "test1.iso"}]})
    requests_mock.get(json_url, text=mock_response_1)

    urls = find_iso_urls(base_url, patterns, cache_file=cache_file)
    assert urls == ["http://example.com/iso_dir/test1.iso"]
    assert cache_file.read_text() == mock_response_1
    assert requests_mock.call_count == 1

    # 2. Second call: Should use the cache (no network request)
    # We change the mock to return something else to prove it's NOT called
    requests_mock.get(json_url, text="STALE")

    urls = find_iso_urls(base_url, patterns, cache_file=cache_file)
    assert urls == ["http://example.com/iso_dir/test1.iso"]
    assert requests_mock.call_count == 1  # Still 1

    # 3. Third call: Cache is old, should fetch and update cache
    # "Aging" the cache file
    old_time = time.time() - 4000
    import os

    os.utime(cache_file, (old_time, old_time))

    mock_response_2 = json.dumps({"data": [{"name": "test2.iso"}]})
    requests_mock.get(json_url, text=mock_response_2)

    urls = find_iso_urls(base_url, patterns, cache_file=cache_file)
    assert urls == ["http://example.com/iso_dir/test2.iso"]
    assert cache_file.read_text() == mock_response_2
    assert requests_mock.call_count == 2
