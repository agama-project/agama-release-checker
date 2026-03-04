import json
import logging
from urllib.parse import urlparse

from agama_release_checker.models import GiteaConfig, GiteaPullRequest
from agama_release_checker.reporting import print_markdown_table
from agama_release_checker.caching import run_cached_command
from agama_release_checker.utils import CACHE_DIR, format_timestamp


class GiteaRequestsReport:
    """Report on open pull requests in a Gitea repository.

    Gitea is a general git technology but in openSUSE context we use it with the
    specific meaning "VCS storing source tarball blobs for OBS".
    """

    def __init__(
        self,
        config: GiteaConfig,
        binary_patterns_by_source: dict[str, list[str]],
        no_cache: bool = False,
    ):
        self.config = config
        self.binary_patterns_by_source = binary_patterns_by_source
        self.no_cache = no_cache

    def _get_repo_path(self, package_name: str) -> str:
        base_url = self.config.url.rstrip("/")
        # https://src.suse.de/pool/ -> pool/package_name
        parsed = urlparse(base_url)
        path = parsed.path.strip("/")
        return f"{path}/{package_name}"

    def _get_login(self) -> str:
        parsed = urlparse(self.config.url)
        return parsed.netloc

    def _fetch_prs(self, package_name: str) -> list[GiteaPullRequest]:
        repo = self._get_repo_path(package_name)
        login = self._get_login()
        branch = self.config.branch
        config_name = self.config.name

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

        cache_dir = CACHE_DIR / "gitea" / config_name / "tea_commands"

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

    def run(self) -> tuple[None, list[GiteaPullRequest]]:
        logging.info(f"Processing Gitea pull requests for: {self.config.name}")
        all_prs: list[GiteaPullRequest] = []
        for package_name in self.binary_patterns_by_source.keys():
            prs = self._fetch_prs(package_name)
            all_prs.extend(prs)
        return None, all_prs

    def render(self, prs: list[GiteaPullRequest]) -> None:
        """Renders the Gitea pull requests report as markdown."""
        print(f"\n## Gitea Pull Requests: {self.config.name}\n")
        print(f"URL: {self.config.url}\n")

        if not prs:
            print("  (No matching pull requests found)")
            return

        headers = [
            "Updated",
            "Index",
            "State",
            "Mergeable",
            "Title",
            "Author",
            "Comments",
        ]
        rows: list[list[str]] = []
        for pr in prs:
            rows.append(
                [
                    format_timestamp(pr.updated_at),
                    f"[{pr.index}]({pr.url})",
                    pr.state,
                    "Yes" if pr.mergeable else "No",
                    pr.title,
                    pr.author,
                    pr.comments,
                ]
            )

        rows.sort(key=lambda x: x[0])
        print_markdown_table(headers, rows)
