from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class BinaryPackage:
    """An RPM binary package found on an ISO or in a repository.

    Fields match the JSON metadata format used in ISO LiveOS/.packages.json.
    """

    name: str
    version: str
    release: str
    arch: str


@dataclass
class SourcePackage:
    """A distro source package in OBS or Gitea.

    Unlike BinaryPackage, source packages have no arch field.
    """

    name: str
    version: str
    release: str


@dataclass
class ObsRequest:
    id: str
    state: str
    source_project: str
    source_package: str
    target_project: str
    target_package: str
    created_at: str
    updated_at: str
    description: str


@dataclass
class GiteaPullRequest:
    index: str
    state: str
    author: str
    url: str
    title: str
    mergeable: bool
    base: str
    created_at: str
    updated_at: str
    comments: str


@dataclass
class RepositoryConfig:
    """Base configuration for a repository entry in config.yml."""

    type: str
    name: str
    url: str


@dataclass
class MirrorcacheConfig(RepositoryConfig):
    """Configuration for a mirrorcache ISO download directory."""

    files: List[str] = field(default_factory=list)


@dataclass
class GitConfig(RepositoryConfig):
    """Configuration for an upstream git source repository."""

    pass


@dataclass
class ObsConfig(RepositoryConfig):
    """Configuration for an OBS project repository."""

    submit_requests: bool = False


@dataclass
class GiteaConfig(RepositoryConfig):
    """Configuration for a Gitea repository.

    Gitea is a general git technology but in openSUSE context we use it with the
    specific meaning "VCS storing source tarball blobs for OBS".
    """

    branch: Optional[str] = None


@dataclass
class AppConfig:
    repositories: List[Dict[str, Any]]
    binary_patterns_by_source: Dict[str, List[str]]
    spec_names_by_package: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def mirrorcache_configs(self) -> List[MirrorcacheConfig]:
        return [
            MirrorcacheConfig(**r)
            for r in self.repositories
            if r.get("type") == "mirrorcache"
        ]

    @property
    def git_configs(self) -> List[GitConfig]:
        return [GitConfig(**r) for r in self.repositories if r.get("type") == "git"]

    @property
    def obs_configs(self) -> List[ObsConfig]:
        return [ObsConfig(**r) for r in self.repositories if r.get("type") == "obs"]

    @property
    def gitea_configs(self) -> List[GiteaConfig]:
        return [GiteaConfig(**r) for r in self.repositories if r.get("type") == "gitea"]
