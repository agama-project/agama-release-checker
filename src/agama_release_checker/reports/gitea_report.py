import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from agama_release_checker.models import SourcePackage
from agama_release_checker.utils import CACHE_DIR, ensure_dir
from agama_release_checker.parsing import parse_obsinfo, parse_spec


class PackagesInGiteaReport:
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
        logging.debug(f"CACHE_DIR={CACHE_DIR}")

    def _get_remote_url(self, package_name: str) -> str:
        base_url = self.config.get("url", "").rstrip("/")
        # https://src.suse.de/pool/agama -> gitea@src.suse.de:pool/agama.git
        url = f"{base_url}/{package_name}"
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        return f"gitea@{parsed.netloc}:{path}.git"

    def _run_git_command(
        self, cmd: List[str], cwd: Optional[Path] = None
    ) -> Tuple[bool, str]:
        display_cwd = str(cwd).replace(str(CACHE_DIR), "$CACHE_DIR") if cwd else "."
        logging.debug(f"Executing git command: {' '.join(cmd)} in {display_cwd}")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")
            return False, e.stderr

    def _fetch_package_data(self, package_name: str) -> Optional[List[SourcePackage]]:
        remote_url = self._get_remote_url(package_name)
        config_name = self.config.get("name", "unknown")
        branch = self.config.get("branch")
        repo_path = CACHE_DIR / "gitea" / config_name / package_name

        if self.no_cache and repo_path.exists():
            import shutil

            shutil.rmtree(repo_path)

        if not repo_path.exists():
            ensure_dir(repo_path.parent)
            # Partial clone: no blobs, shallow, sparse
            cmd = [
                "git",
                "clone",
                "--filter=blob:none",
                "--sparse",
                "--depth",
                "1",
            ]
            if branch:
                cmd.extend(["--branch", branch])

            cmd.extend([remote_url, str(repo_path)])

            success, _ = self._run_git_command(cmd)
            if not success:
                return None

            # Initialize sparse-checkout in no-cone mode
            self._run_git_command(
                ["git", "sparse-checkout", "init", "--no-cone"], cwd=repo_path
            )

        else:
            # Repo exists, update it.
            # We use fetch + reset --hard to ensure we have the latest commit and a clean state.
            # This is safe regarding binary blobs because git reset --hard respects the
            # current sparse-checkout patterns, which should only include small text files
            # from the previous run.
            fetch_cmd = ["git", "fetch", "--depth", "1", "origin"]
            if branch:
                fetch_cmd.append(branch)

            self._run_git_command(fetch_cmd, cwd=repo_path)
            self._run_git_command(
                ["git", "reset", "--hard", "FETCH_HEAD"], cwd=repo_path
            )

            # Ensure no-cone mode is set (idempotent if already set)
            self._run_git_command(
                ["git", "sparse-checkout", "init", "--no-cone"], cwd=repo_path
            )

        # Get list of files in the repo
        success, output = self._run_git_command(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"], cwd=repo_path
        )
        if not success:
            return None

        repo_files = set(output.splitlines())

        # Determine which files to checkout
        files_to_get = []

        # logic for obsinfo similar to obs_report
        obsinfo_file = None
        target_obsinfo = f"{package_name}.obsinfo"
        if target_obsinfo in repo_files:
            obsinfo_file = target_obsinfo
        else:
            # Fallback to any .obsinfo
            for f in repo_files:
                if f.endswith(".obsinfo"):
                    obsinfo_file = f
                    break

        if obsinfo_file:
            files_to_get.append(obsinfo_file)

        spec_basenames = self.spec_names_by_package.get(package_name, [package_name])
        for spec in spec_basenames:
            spec_file = f"{spec}.spec"
            if spec_file in repo_files:
                files_to_get.append(spec_file)

        if not files_to_get:
            return []

        # Sparse checkout only needed files
        # We use --no-cone implicitly because we init'd with it or just set files
        # But explicitly setting it in set command is also good or just passing files
        # checking if init --no-cone persists. yes it should.
        # But 'set' command might overwrite patterns.
        # SAFE way: git sparse-checkout set --no-cone file1 file2
        self._run_git_command(
            ["git", "sparse-checkout", "set", "--no-cone"] + files_to_get, cwd=repo_path
        )

        # Read contents
        shared_version = ""
        if obsinfo_file:
            obsinfo_path = repo_path / obsinfo_file
            if obsinfo_path.exists():
                content = obsinfo_path.read_text()
                shared_version = parse_obsinfo(content) or ""

        packages: List[SourcePackage] = []
        for spec_basename in spec_basenames:
            version = shared_version
            release = "0"

            spec_file = f"{spec_basename}.spec"
            spec_path = repo_path / spec_file
            if spec_path.exists():
                content = spec_path.read_text()
                v, r = parse_spec(content)
                if v and v != "0":
                    version = v
                    release = r
                elif v == "0" and not version:
                    version = "0"
                    release = r

            if version:
                packages.append(
                    SourcePackage(
                        name=spec_basename,
                        version=version,
                        release=release,
                    )
                )
        return packages

    def run(self) -> Tuple[Optional[str], Optional[List[SourcePackage]]]:
        logging.info(f"Processing Gitea project: {self.config.get('name')}")
        all_packages: List[SourcePackage] = []
        for package_name in self.binary_patterns_by_source.keys():
            pkgs = self._fetch_package_data(package_name)
            if pkgs:
                all_packages.extend(pkgs)

        return None, all_packages
