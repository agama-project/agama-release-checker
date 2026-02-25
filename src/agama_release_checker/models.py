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
class StageConfig:
    type: str
    name: str
    url: str


@dataclass
class MirrorcacheConfig(StageConfig):
    files: List[str] = field(default_factory=list)


@dataclass
class GitConfig(StageConfig):
    pass


@dataclass
class GiteaConfig(StageConfig):
    branch: Optional[str] = None


@dataclass
class AppConfig:
    stages: List[Dict[str, Any]]
    rpms: Dict[str, List[str]]
    specs: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def mirrorcache_configs(self) -> List[MirrorcacheConfig]:
        return [
            MirrorcacheConfig(**s)
            for s in self.stages
            if s.get("type") == "mirrorcache"
        ]

    @property
    def git_configs(self) -> List[GitConfig]:
        return [GitConfig(**s) for s in self.stages if s.get("type") == "git"]

    @property
    def gitea_configs(self) -> List[GiteaConfig]:
        return [
            GiteaConfig(**s) for s in self.stages if s.get("type") == "giteaproject"
        ]
