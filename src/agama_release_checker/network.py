import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore
import fnmatch

from .utils import ensure_dir


def cached_get(url: str, cache_file: Optional[Path] = None) -> Optional[str]:
    """
    Fetches the content of a URL, using a cache file if available and fresh.
    """
    content = ""
    if cache_file and cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < 3600:
            logging.info(f"Using cached index: {cache_file}")
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
    base_url: str, patterns: List[str], cache_file: Optional[Path] = None
) -> List[str]:
    """Scrapes the given URL and returns a list of matching ISO URLs."""
    logging.info(f"Fetching ISO directory from: {base_url}")
    logging.debug(f"Scraping with patterns: {patterns}")

    content = cached_get(base_url, cache_file)
    if content is None:
        return []

    soup = BeautifulSoup(content, "html.parser")
    iso_urls = []
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag["href"])
        filename = href.split("/")[-1]
        for pattern in patterns:
            if fnmatch.fnmatch(filename, pattern):
                iso_urls.append(urljoin(base_url, href))
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
