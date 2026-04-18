"""Shared fixtures for release-dashboard tests."""

from __future__ import annotations

import pytest

from release_dashboard_mcp.config import AppConfig, Ev2ApiConfig, StageConfig
from release_dashboard_mcp.auth import Ev2Auth
from release_dashboard_mcp.ev2_client import Ev2Client
from release_dashboard_mcp.models import (
    ActionDetail,
    ActionOperationInfo,
    ErrorInfo,
    RegionDisplayInfo,
    ResourceDetail,
    ResourceOperation,
    Rollout,
    RolloutDetails,
    RolloutOperationInfo,
    RolloutResourceGroup,
    RolloutDisplayInfo,
    ServiceGroupDisplayInfo,
    StageDisplayInfo,
)


# ---------------------------------------------------------------------------
# Config / Auth / Client
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_config() -> AppConfig:
    return AppConfig(
        ev2_api=Ev2ApiConfig(
            base_url="https://ev2.test/api",
            api_version="2016-07-01",
            resource_id="https://ev2.test",
            service_identifier="test-sid",
            rollout_lookback_days=21,
        ),
        service_groups=["SG.Alpha", "SG.Beta"],
        stages=[
            StageConfig(name="Stage 1", regions=["eastus2euap"]),
            StageConfig(name="Stage 2", regions=["canadacentral", "francecentral"]),
            StageConfig(name="Stage 3", regions=["REMAINING_REGIONS"]),
        ],
    )


@pytest.fixture()
def mock_auth(monkeypatch):
    """Return an Ev2Auth whose get_token always resolves to a fake token."""

    class _FakeCredential:
        def get_token(self, scope):
            class _T:
                token = "fake-token"
            return _T()

    auth = Ev2Auth.__new__(Ev2Auth)
    auth._scope = "https://ev2.test/.default"
    auth._credential = _FakeCredential()
    return auth


@pytest.fixture()
def client(app_config, mock_auth) -> Ev2Client:
    return Ev2Client(app_config, mock_auth)


# ---------------------------------------------------------------------------
# Raw API response factories
# ---------------------------------------------------------------------------

def _make_raw_rollout(
    *,
    rollout_id: str = "r-001",
    status: str = "Completed",
    service_group: str = "SG.Alpha",
    environment: str = "Prod",
    build_version: str = "1.2.3",
    start_time: str = "2026-03-01T00:00:00Z",
    resource_groups: list | None = None,
) -> dict:
    """Build a raw EV2 rollout JSON dict matching the API shape."""
    return {
        "rolloutId": rollout_id,
        "status": status,
        "rolloutDetails": {
            "serviceGroup": service_group,
            "environment": environment,
            "buildVersion": build_version,
        },
        "rolloutOperationInfo": {
            "retryAttempt": 0,
            "skipSucceededOnRetry": False,
            "startTime": start_time,
        },
        "resourceGroups": resource_groups or [],
    }


def _make_resource_group(
    *,
    name: str = "rg-1",
    location: str = "eastus2euap",
    actions: list[dict] | None = None,
) -> dict:
    action_list = actions or [
        {
            "name": "Deploy",
            "stepName": "step1",
            "status": "Succeeded",
            "actionOperationInfo": {
                "correlationId": "corr-1",
                "deploymentName": "dep-1",
                "startTime": "2026-03-01T01:00:00Z",
                "endTime": "2026-03-01T02:00:00Z",
                "lastUpdatedTime": "2026-03-01T02:00:00Z",
            },
            "resourceOperations": [
                {
                    "resourceName": "res-1",
                    "resourceType": "type-1",
                    "provisioningState": "Succeeded",
                    "statusMessage": "",
                    "statusCode": "200",
                    "mode": "Incremental",
                }
            ],
        }
    ]
    return {
        "name": name,
        "azureResourceGroupName": f"azure-{name}",
        "location": location,
        "lastUpdatedTime": "2026-03-01T02:00:00Z",
        "subscriptionId": "sub-001",
        "resources": [
            {
                "name": "resource-1",
                "location": location,
                "actions": action_list,
            }
        ],
    }
