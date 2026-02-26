from pathlib import Path
import yaml  # type: ignore
from .models import AppConfig, RepositoryConfig


def load_config(config_path: Path) -> AppConfig:
    """Loads and returns the YAML configuration from the given path."""
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    data["repositories"] = [RepositoryConfig.from_dict(r) for r in data["repositories"]]
    return AppConfig(**data)
