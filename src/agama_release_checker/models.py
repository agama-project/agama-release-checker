from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import yaml  # type: ignore


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

    name: str
    url: str
    internal: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RepositoryConfig":
        """Deserialize a raw YAML dict into the appropriate subclass.

        The 'type' key selects the subclass; unknown keys are ignored.
        """
        d = dict(d)
        type_name = str(d.pop("type", ""))
        subcls = _CONFIG_CLASSES.get(type_name)
        if subcls is None:
            raise ValueError(f"Unknown repository type: {type_name!r}")
        known = {f.name for f in subcls.__dataclass_fields__.values()}
        return subcls(**{k: v for k, v in d.items() if k in known})


@dataclass
class MirrorcacheConfig(RepositoryConfig):
    """Configuration for a mirrorcache ISO download directory."""

    files: list[str] = field(default_factory=list)


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

    branch: str | None = None


_CONFIG_CLASSES: dict[str, type[RepositoryConfig]] = {
    "mirrorcache": MirrorcacheConfig,
    "git": GitConfig,
    "obs": ObsConfig,
    "gitea": GiteaConfig,
}


@dataclass
class AppConfig:
    """Top-level application configuration loaded from config.yml."""

    repositories: list[RepositoryConfig]
    binary_patterns_by_source: dict[str, list[str]]
    spec_names_by_package: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, config_path: Path) -> "AppConfig":
        """Loads and returns the YAML configuration from the given path."""
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
        data["repositories"] = [
            RepositoryConfig.from_dict(r) for r in data["repositories"]
        ]
        return cls(**data)

    @property
    def mirrorcache_configs(self) -> list[MirrorcacheConfig]:
        return [r for r in self.repositories if isinstance(r, MirrorcacheConfig)]

    @property
    def git_configs(self) -> list[GitConfig]:
        return [r for r in self.repositories if isinstance(r, GitConfig)]

    @property
    def obs_configs(self) -> list[ObsConfig]:
        return [r for r in self.repositories if isinstance(r, ObsConfig)]

    @property
    def gitea_configs(self) -> list[GiteaConfig]:
        return [r for r in self.repositories if isinstance(r, GiteaConfig)]
