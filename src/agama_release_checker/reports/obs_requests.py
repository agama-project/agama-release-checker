import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from agama_release_checker.models import ObsRequest
from agama_release_checker.utils import CACHE_DIR
from agama_release_checker.caching import run_cached_command


class ObsSubmitRequestsReport:
    def __init__(
        self,
        config: Dict[str, Any],
        binary_patterns_by_source: Dict[str, List[str]],
        no_cache: bool = False,
        recent_requests: bool = False,
    ):
        self.config = config
        self.binary_patterns_by_source = binary_patterns_by_source
        self.no_cache = no_cache
        self.recent_requests = recent_requests

    def _get_project_name(self) -> str:
        url = self.config.get("url", "")
        if not url:
            return ""
        # Handle cases where URL might end with slash
        path = urlparse(url).path.strip("/")
        # Expected format: /project/show/<project_name>
        parts = path.split("/")
        return parts[-1]

    def _run_osc_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Runs an osc command and returns success status and output, with caching."""

        # Don't cache 'osc version'
        if cmd == ["osc", "version"]:
            return run_cached_command(cmd, cache_dir=None)

        # Directory structure: CACHE_DIR/obs/repo_name/osc_requests/
        repo_name = self.config.get("name", "unknown")
        cache_dir = CACHE_DIR / "obs" / repo_name / "osc_requests"

        # run_cached_command will handle directory creation and caching
        return run_cached_command(cmd, cache_dir=cache_dir, force_refresh=self.no_cache)

    def run(self) -> Tuple[Optional[str], Optional[List[ObsRequest]]]:
        project = self._get_project_name()
        if not project:
            logging.error(
                f"Could not determine OBS project name from URL: {self.config.get('url')}"
            )
            return None, None

        logging.info(f"Processing OBS requests for project: {project}")

        # check for osc availability once
        if not self._run_osc_command(["osc", "version"])[0]:
            return None, None

        requests: List[ObsRequest] = []

        # Iterate over all defined source packages
        for package_name in self.binary_patterns_by_source.keys():
            if self.recent_requests:
                cutoff_date = (datetime.now() - timedelta(weeks=2)).strftime("%Y-%m-%d")
                query = (
                    f"state/@when>'{cutoff_date}'"
                    f"+and+action/target/@project='{project}'"
                    f"+and+action/target/@package='{package_name}'"
                )
            else:
                # Construct API query for "new", "review", "declined" requests
                query = (
                    f"(state/@name='new'+or+state/@name='review'+or+state/@name='declined')"
                    f"+and+action/target/@project='{project}'"
                    f"+and+action/target/@package='{package_name}'"
                )

            # osc api expects just the path part for the command, but we need to pass arguments.
            # However, 'osc api' takes the path as an argument.
            # cmd = ["osc", "api", f"/search/request?match={query}"]
            # Wait, 'osc api' documentation or usage: osc api [URL]
            # When using shell, we quote the URL. Here we pass it as a list item.

            # The previous 'osc' command wrapper handles executing the list.
            cmd = ["osc", "api", f"/search/request?match={query}"]

            success, output = self._run_osc_command(cmd)
            if not success:
                logging.warning(
                    f"Failed to fetch requests for package {package_name} in {project}"
                )
                continue

            try:
                root = ET.fromstring(output)
                for req_elem in root.findall("request"):
                    req_id = req_elem.get("id") or ""

                    state_elem = req_elem.find("state")
                    state_name = (
                        state_elem.get("name") if state_elem is not None else "unknown"
                    ) or "unknown"
                    created_at = (
                        state_elem.get("created") if state_elem is not None else ""
                    ) or ""
                    # "when" is updated time?
                    updated_at = (
                        state_elem.get("when") if state_elem is not None else ""
                    ) or ""

                    action_elem = req_elem.find("action")
                    if action_elem is None:
                        continue

                    source_elem = action_elem.find("source")
                    source_project = (
                        source_elem.get("project") if source_elem is not None else ""
                    ) or ""
                    source_package = (
                        source_elem.get("package") if source_elem is not None else ""
                    ) or ""

                    target_elem = action_elem.find("target")
                    target_project = (
                        target_elem.get("project") if target_elem is not None else ""
                    ) or ""
                    target_package = (
                        target_elem.get("package") if target_elem is not None else ""
                    ) or ""

                    description = req_elem.findtext("description") or ""

                    requests.append(
                        ObsRequest(
                            id=req_id,
                            state=state_name,
                            source_project=source_project,
                            source_package=source_package,
                            target_project=target_project,
                            target_package=target_package,
                            created_at=created_at,
                            updated_at=updated_at,
                            description=description.strip(),
                        )
                    )

            except ET.ParseError:
                logging.error(
                    f"Failed to parse XML response for package {package_name}"
                )

        return None, requests
