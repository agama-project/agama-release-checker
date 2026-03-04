import logging
import subprocess
from pathlib import Path

from .utils import CACHE_DIR, ensure_dir


class GitManager:
    def __init__(self, repo_url: str, repo_name: str):
        self.repo_url = repo_url
        self.repo_path = CACHE_DIR / "git" / repo_name

    def update_repo(self) -> None:
        """Clones or updates the git repository."""
        if self.repo_path.exists():
            logging.info(f"Updating git repo in {self.repo_path}")
            try:
                # Ensure the repo is configured as a mirror if it wasn't
                subprocess.run(
                    [
                        "git",
                        "config",
                        "--replace-all",
                        "remote.origin.fetch",
                        "+refs/*:refs/*",
                    ],
                    cwd=str(self.repo_path),
                    check=True,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                subprocess.run(
                    ["git", "fetch", "--prune"],
                    cwd=str(self.repo_path),
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to update git repo: {e.stderr}")
        else:
            logging.info(f"Cloning git repo to {self.repo_path}")
            ensure_dir(self.repo_path.parent)
            try:
                subprocess.run(
                    ["git", "clone", "--mirror", self.repo_url, str(self.repo_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to clone git repo: {e.stderr}")

    def get_commit_info(self, commit_hash: str) -> tuple[str | None, str | None]:
        """Returns (timestamp, description) for a commit hash."""
        if not self.repo_path.exists():
            return None, None

        timestamp = None
        description = None

        try:
            # Timestamp: ISO 8601-like format
            ts_proc = subprocess.run(
                ["git", "show", "-s", "--format=%ci", commit_hash],
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True,
            )
            timestamp = ts_proc.stdout.strip()
        except subprocess.CalledProcessError:
            pass  # Commit might not be found

        try:
            # Description: git describe
            desc_proc = subprocess.run(
                [
                    "git",
                    "describe",
                    "--tags",
                    commit_hash,
                ],  # Use --tags to find any tag
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True,
            )
            description = desc_proc.stdout.strip()
        except subprocess.CalledProcessError as e:
            # git describe fails if no tags are reachable or found
            if e.stderr and "No names found" in e.stderr:
                description = "(no tags)"
            else:
                pass

        return timestamp, description
