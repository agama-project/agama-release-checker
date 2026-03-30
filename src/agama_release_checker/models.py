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
class GitTimestamp:
    """The timestamp of a git commit.

    Currently just a formatted string, but encapsulated for future expansion.
    """

    formatted: str


@dataclass
class GitRevisionTimestamps:
    """A collection of timestamps for git revisions, keyed by git hash."""

    timestamps: dict[str, GitTimestamp] = field(default_factory=dict)

    def get(self, githash: str) -> GitTimestamp | None:
        return self.timestamps.get(githash)


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
class GiteaSubmitStrategy:
    """Custom strategy for submitting a package to Gitea.

    1. Check out source_repo
    2. Run source_run
    3. Check out target_repo
    4. Copy source_repo/source_dir to target_repo/target_dir
    (also make a branch and a PR, like with the regular strategy)
    """

    source_repo: str
    source_run: str
    source_dir: str
    target_repo: str
    target_dir: str
    target_branch: str | None = None
    fork_org: str | None = None


@dataclass
class PackageSubmissionConfig:
    # ... (no change to from_dict needed as it already filters by known fields)
    gitea_submit: GiteaSubmitStrategy | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PackageSubmissionConfig":
        d = dict(d)
        if "gitea_submit" in d and isinstance(d["gitea_submit"], dict):
            # Pass only known fields to GiteaSubmitStrategy
            known = {f.name for f in GiteaSubmitStrategy.__dataclass_fields__.values()}
            strat_data = {k: v for k, v in d["gitea_submit"].items() if k in known}
            d["gitea_submit"] = GiteaSubmitStrategy(**strat_data)
        return cls(**d)


@dataclass
class ObsSubmissionsConfig:
    """Default source and target projects for OBS submissions."""

    source_project: str
    target_project: str


@dataclass
class GiteaSubmissionsConfig:
    """Default source project, target org and branch for Gitea submissions."""

    source_project: str
    target_org: str
    target_branch: str
    fork_org: str | None = None


@dataclass
class MakerConfig:
    """Configuration for agama-release-maker."""

    package_submissions: dict[str, PackageSubmissionConfig]
    obs_submissions: ObsSubmissionsConfig
    gitea_submissions: GiteaSubmissionsConfig

    @classmethod
    def from_file(cls, config_path: Path) -> "MakerConfig":
        """Loads and returns the YAML configuration from the given path."""
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        if "package_submissions" in data:
            data["package_submissions"] = {
                k: PackageSubmissionConfig.from_dict(v or {})
                for k, v in data["package_submissions"].items()
            }

        if "obs_submissions" in data:
            data["obs_submissions"] = ObsSubmissionsConfig(**data["obs_submissions"])

        if "gitea_submissions" in data:
            data["gitea_submissions"] = GiteaSubmissionsConfig(
                **data["gitea_submissions"]
            )

        return cls(**data)


@dataclass
class AppConfig:
    """Top-level application configuration loaded from config.yml."""

    repositories: list[RepositoryConfig]
    package_submissions: dict[str, PackageSubmissionConfig] = field(
        default_factory=dict
    )
    binary_patterns_by_source: dict[str, list[str]] = field(default_factory=dict)
    spec_names_by_package: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, config_path: Path) -> "AppConfig":
        """Loads and returns the YAML configuration from the given path."""
        with open(config_path, "r") as f:
            data = yaml.safe_load(f)
        data["repositories"] = [
            RepositoryConfig.from_dict(r) for r in data["repositories"]
        ]
        if "package_submissions" in data:
            data["package_submissions"] = {
                k: PackageSubmissionConfig.from_dict(v or {})
                for k, v in data["package_submissions"].items()
            }

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
