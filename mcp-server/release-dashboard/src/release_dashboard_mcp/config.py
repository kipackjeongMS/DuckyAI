"""Configuration loader for Release Dashboard MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Ev2ApiConfig:
    base_url: str = "https://azureservicedeploy.msft.net/api"
    api_version: str = "2016-07-01"
    resource_id: str = "https://azureservicedeploy.msft.net"
    scope: str = "https://azureservicedeploy.msft.net/Rollouts.ReadWrite.User"
    service_identifier: str = ""
    rollout_lookback_days: int = 21


@dataclass
class AuthConfig:
    client_id: str = ""
    authority: str = ""


@dataclass
class StageConfig:
    name: str = ""
    regions: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    ev2_api: Ev2ApiConfig = field(default_factory=Ev2ApiConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    service_groups: list[str] = field(default_factory=list)
    stages: list[StageConfig] = field(default_factory=list)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = os.environ.get(
            "RELEASE_DASHBOARD_CONFIG",
            Path(__file__).resolve().parent.parent.parent / "config.yaml",
        )
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text())

    ev2 = raw.get("ev2_api", {})
    auth = raw.get("auth", {})

    return AppConfig(
        ev2_api=Ev2ApiConfig(
            base_url=ev2.get("base_url", Ev2ApiConfig.base_url),
            api_version=ev2.get("api_version", Ev2ApiConfig.api_version),
            resource_id=ev2.get("resource_id", Ev2ApiConfig.resource_id),
            scope=ev2.get("scope", Ev2ApiConfig.scope),
            service_identifier=ev2.get("service_identifier", ""),
            rollout_lookback_days=ev2.get("rollout_lookback_days", 21),
        ),
        auth=AuthConfig(
            client_id=auth.get("client_id", ""),
            authority=auth.get("authority", ""),
        ),
        service_groups=raw.get("service_groups", []),
        stages=[
            StageConfig(name=s.get("name", ""), regions=s.get("regions", []))
            for s in raw.get("stages", [])
        ],
    )
