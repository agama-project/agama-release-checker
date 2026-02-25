import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from agama_release_checker.models import GiteaPullRequest
from agama_release_checker.caching import run_cached_command
from agama_release_checker.utils import CACHE_DIR


class GiteaPullRequestsReport:
    def __init__(
        self,
        config: Dict[str, Any],
        binary_patterns_by_source: Dict[str, List[str]],
        no_cache: bool = False,
    ):
        self.config = config
        self.binary_patterns_by_source = binary_patterns_by_source
        self.no_cache = no_cache

    def _get_repo_path(self, package_name: str) -> str:
        base_url = self.config.get("url", "").rstrip("/")
        # https://src.suse.de/pool/ -> pool/package_name
        parsed = urlparse(base_url)
        path = parsed.path.strip("/")
        return f"{path}/{package_name}"

    def _get_login(self) -> str:
        url = self.config.get("url", "")
        parsed = urlparse(url)
        return parsed.netloc

    def _fetch_prs(self, package_name: str) -> List[GiteaPullRequest]:
        repo = self._get_repo_path(package_name)
        login = self._get_login()
        branch = self.config.get("branch")
        stage_name = self.config.get("name", "unknown")

        cmd = [
            "tea",
            "pr",
            "--login",
            login,
            "--repo",
            repo,
            "--output",
            "json",
            "-f",
            "index,state,author,url,title,mergeable,base,created,updated,comments",
        ]

        cache_dir = CACHE_DIR / "giteaproject" / stage_name / "tea_commands"

        try:
            success, output = run_cached_command(
                cmd, cache_dir=cache_dir, force_refresh=self.no_cache
            )

            if not success:
                logging.error(f"Tea command failed for {repo}: {output.strip()}")
                return []

            data = json.loads(output)
            prs = []
            for item in data:
                # Filter by branch if specified
                if branch and item.get("base") != branch:
                    continue

                prs.append(
                    GiteaPullRequest(
                        index=item.get("index", ""),
                        state=item.get("state", ""),
                        author=item.get("author", ""),
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        mergeable=item.get("mergeable") == "true",
                        base=item.get("base", ""),
                        created_at=item.get("created", ""),
                        updated_at=item.get("updated", ""),
                        comments=item.get("comments", "0"),
                    )
                )
            return prs
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode tea output for {repo}: {e}")
            return []

    def run(self) -> Tuple[None, List[GiteaPullRequest]]:
        logging.info(f"Processing Gitea pull requests for: {self.config.get('name')}")
        all_prs: List[GiteaPullRequest] = []
        for package_name in self.binary_patterns_by_source.keys():
            prs = self._fetch_prs(package_name)
            all_prs.extend(prs)
        return None, all_prs
