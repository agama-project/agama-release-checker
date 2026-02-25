import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from urllib.parse import urlparse

from agama_release_checker.models import SourcePackage
from agama_release_checker.utils import CACHE_DIR
from agama_release_checker.caching import run_cached_command
from agama_release_checker.parsing import parse_obsinfo, parse_spec


class PackagesInObsReport:
    def __init__(
        self,
        config: Dict[str, Any],
        binary_patterns_by_source: Dict[str, List[str]],
        spec_names_by_package: Optional[Dict[str, List[str]]] = None,
        no_cache: bool = False,
    ):
        self.config = config
        self.binary_patterns_by_source = binary_patterns_by_source
        self.spec_names_by_package = spec_names_by_package or {}
        self.no_cache = no_cache

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

        # Directory structure: CACHE_DIR/obs/repo_name/osc_commands/
        repo_name = self.config.get("name", "unknown")
        cache_dir = CACHE_DIR / "obs" / repo_name / "osc_commands"

        # run_cached_command will handle directory creation and caching
        return run_cached_command(cmd, cache_dir=cache_dir, force_refresh=self.no_cache)

    def _get_project_packages(self, project: str) -> Set[str]:
        success, output = self._run_osc_command(["osc", "ls", project])
        if success:
            return set(output.splitlines())
        return set()

    def _get_package_files(self, project: str, package: str) -> List[str]:
        success, output = self._run_osc_command(["osc", "ls", project, package])
        if success:
            return output.splitlines()
        return []

    def _read_file_content(self, project: str, package: str, filename: str) -> str:
        success, output = self._run_osc_command(
            ["osc", "cat", project, package, filename]
        )
        if success:
            return output
        return ""

    def run(self) -> Tuple[Optional[str], Optional[List[SourcePackage]]]:
        project = self._get_project_name()
        if not project:
            logging.error(
                f"Could not determine OBS project name from URL: {self.config.get('url')}"
            )
            return None, None

        logging.info(f"Processing OBS project: {project}")

        # check for osc availability once
        if not self._run_osc_command(["osc", "version"])[0]:
            return None, None

        project_packages = self._get_project_packages(project)
        if not project_packages:
            logging.warning(
                f"No packages found in project {project} or failed to list."
            )
            return None, None

        packages: List[SourcePackage] = []

        for package_name in self.binary_patterns_by_source.keys():
            if package_name not in project_packages:
                logging.debug(f"Package {package_name} not found in {project}")
                continue

            files = self._get_package_files(project, package_name)
            if not files:
                continue

            # Shared version from .obsinfo if any
            shared_version = ""
            obsinfo_files = [f for f in files if f.endswith(".obsinfo")]
            target_obsinfo = f"{package_name}.obsinfo"
            if target_obsinfo in obsinfo_files:
                obsinfo_file = target_obsinfo
            elif obsinfo_files:
                obsinfo_file = obsinfo_files[0]
            else:
                obsinfo_file = None

            if obsinfo_file:
                content = self._read_file_content(project, package_name, obsinfo_file)
                shared_version = parse_obsinfo(content) or ""

            spec_basenames = self.spec_names_by_package.get(
                package_name, [package_name]
            )

            for spec_basename in spec_basenames:
                version = shared_version
                release = "0"

                spec_file = f"{spec_basename}.spec"
                if spec_file in files:
                    content = self._read_file_content(project, package_name, spec_file)
                    v, r = parse_spec(content)

                    if v and v != "0":
                        version = v
                        release = r
                    elif v == "0" and not version:
                        version = "0"
                        release = r
                    elif not v and not version:
                        # try to get version if we have it from obsinfo but no spec version found?
                        pass
                else:
                    # if spec file not found, but we had shared_version, should we still report it?
                    # maybe only if it was intended to be there.
                    pass

                if version:
                    packages.append(
                        SourcePackage(
                            name=spec_basename,
                            version=version,
                            release=release,
                        )
                    )

        return None, packages
