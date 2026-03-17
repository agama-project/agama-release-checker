import logging
import subprocess
import sys
import time
import json
from pathlib import Path
from urllib.parse import urljoin

import requests  # type: ignore
import fnmatch

from .utils import ensure_dir


def cached_get(url: str, cache_file: Path | None = None) -> str | None:
    """
    Fetches the content of a URL, using a cache file if available and fresh.
    """
    content = ""
    if cache_file and cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < 3600:
            logging.info(f"In cache: {cache_file}")
            try:
                with open(cache_file, "r") as f:
                    content = f.read()
            except OSError as e:
                logging.warning(f"Failed to read cache file {cache_file}: {e}")

    if not content:
        try:
            response = requests.get(url, timeout=15)  # 15 seconds
            response.raise_for_status()
            content = response.text

            if cache_file:
                ensure_dir(cache_file.parent)
                try:
                    with open(cache_file, "w") as f:
                        f.write(content)
                except OSError as e:
                    logging.warning(f"Failed to write cache file {cache_file}: {e}")

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching URL {url}: {e}")
            return None
    return content


def find_iso_urls(
    base_url: str, patterns: list[str], cache_file: Path | None = None
) -> list[str]:
    """Scrapes the given URL and returns a list of matching ISO URLs."""
    logging.info(f"Fetching ISO directory from: {base_url}")
    logging.debug(f"Scraping with patterns: {patterns}")

    # Use Mirrorcache's ?jsontable for easier parsing
    if "?" in base_url:
        json_url = f"{base_url}&jsontable"
    else:
        json_url = f"{base_url}?jsontable"

    content = cached_get(json_url, cache_file)
    if content is None:
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON from {json_url}: {e}")
        return []

    iso_urls = []
    # data["data"] contains list of files: {"name": "...", "mtime": ..., "size": ...}
    for item in data.get("data", []):
        filename = item.get("name")
        if not filename:
            continue
        for pattern in patterns:
            if fnmatch.fnmatch(filename, pattern):
                iso_urls.append(urljoin(base_url, filename))
                break
    logging.debug(f"Found {len(iso_urls)} ISO URLs.")
    return iso_urls


def download_file(url: str, destination_path: Path) -> bool:
    """Downloads a file from a URL using curl."""
    logging.info(f"Dowloading to {destination_path} from {url} with curl.")
    try:
        command = ["curl", "-L", url, "-o", str(destination_path), "--progress-bar"]
        subprocess.run(command, check=True, stdout=sys.stdout, stderr=sys.stderr)
        logging.info(f"Success: {destination_path.name}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logging.error(f"Download failed: {e}")
        return False
