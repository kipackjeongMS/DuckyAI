"""EV2 API client — fetches rollout data and transforms it into display models."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .auth import Ev2Auth
from .config import AppConfig, StageConfig
from .models import (
    ActionDetail,
    ActionOperationInfo,
    ErrorInfo,
    RegionDisplayInfo,
    ResourceDetail,
    ResourceOperation,
    Rollout,
    RolloutDetails,
    RolloutDisplayInfo,
    RolloutOperationInfo,
    RolloutResourceGroup,
    ServiceGroupDisplayInfo,
    StageDisplayInfo,
)

_TIMEOUT = 30.0


class Ev2Client:
    """HTTP client for the EV2 Rollout Infrastructure API."""

    def __init__(self, config: AppConfig, auth: Ev2Auth) -> None:
        self._config = config
        self._auth = auth
        self._base = config.ev2_api.base_url.rstrip("/")
        self._version = config.ev2_api.api_version

    # ------------------------------------------------------------------
    # Low-level API calls
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        token = await self._auth.get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params=params)
            if not resp.is_success:
                body = resp.text
                raise RuntimeError(f"EV2 API error {resp.status_code}: {body[:500]}")
            return resp.json()

    async def list_rollouts(self, service_group: str, start_from: datetime, start_to: datetime) -> list[dict]:
        params = {
            "servicegroupname": service_group,
            "startTimeFrom": start_from.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "startTimeTo": start_to.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "api-version": self._version,
        }
        data = await self._get("/rollouts", params)
        return data if isinstance(data, list) else data.get("value", [])

    async def get_rollout(self, rollout_id: str, service_group: str) -> dict:
        params = {
            "servicegroupname": service_group,
            "api-version": self._version,
            "embed-detail": "true",
        }
        return await self._get(f"/rollouts/{rollout_id}", params)

    # ------------------------------------------------------------------
    # Parsing helpers (raw JSON → dataclasses)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_error_info(d: dict | None) -> ErrorInfo | None:
        if not d:
            return None
        return ErrorInfo(
            status_code=d.get("statusCode", 0),
            error_code=d.get("errorCode", ""),
            error_reason=d.get("errorReason", ""),
            help_link=d.get("helpLink", ""),
            incident_link=d.get("incidentLink", ""),
            escalate_to=d.get("escalateTo", ""),
            escalate_info=d.get("escalateInfo", ""),
        )

    @staticmethod
    def _parse_action_op_info(d: dict | None) -> ActionOperationInfo | None:
        if not d:
            return None
        return ActionOperationInfo(
            correlation_id=d.get("correlationId", ""),
            deployment_name=d.get("deploymentName", ""),
            start_time=d.get("startTime"),
            end_time=d.get("endTime"),
            last_updated_time=d.get("lastUpdatedTime"),
            error_info=Ev2Client._parse_error_info(d.get("errorInfo")),
        )

    @staticmethod
    def _parse_rollout(data: dict) -> Rollout:
        details_raw = data.get("rolloutDetails") or {}
        op_info_raw = data.get("rolloutOperationInfo") or {}
        rgs_raw = data.get("resourceGroups") or []

        resource_groups = []
        for rg in rgs_raw:
            resources = []
            for res in rg.get("resources", []):
                actions = []
                for act in res.get("actions", []):
                    actions.append(ActionDetail(
                        name=act.get("name", ""),
                        step_name=act.get("stepName", ""),
                        status=act.get("status", ""),
                        action_operation_info=Ev2Client._parse_action_op_info(act.get("actionOperationInfo")),
                        resource_operations=[
                            ResourceOperation(
                                resource_name=ro.get("resourceName", ""),
                                resource_type=ro.get("resourceType", ""),
                                provisioning_state=ro.get("provisioningState", ""),
                                status_message=ro.get("statusMessage", ""),
                                status_code=ro.get("statusCode", ""),
                                mode=ro.get("mode", ""),
                            )
                            for ro in act.get("resourceOperations", [])
                        ],
                    ))
                resources.append(ResourceDetail(
                    name=res.get("name", ""),
                    location=res.get("location", ""),
                    actions=actions,
                ))
            resource_groups.append(RolloutResourceGroup(
                name=rg.get("name", ""),
                azure_resource_group_name=rg.get("azureResourceGroupName", ""),
                location=rg.get("location", ""),
                last_updated_time=rg.get("lastUpdatedTime"),
                subscription_id=rg.get("subscriptionId", ""),
                resources=resources,
            ))

        return Rollout(
            rollout_id=data.get("rolloutId", ""),
            status=data.get("status", ""),
            rollout_details=RolloutDetails(
                service_group=details_raw.get("serviceGroup", ""),
                environment=details_raw.get("environment", ""),
                build_version=details_raw.get("buildVersion", ""),
            ),
            rollout_operation_info=RolloutOperationInfo(
                retry_attempt=op_info_raw.get("retryAttempt", 0),
                skip_succeeded_on_retry=op_info_raw.get("skipSucceededOnRetry", False),
                start_time=op_info_raw.get("startTime"),
            ),
            resource_groups=resource_groups,
        )

    # ------------------------------------------------------------------
    # Business logic (mirrors RolloutService.cs)
    # ------------------------------------------------------------------

    def _build_region_info(self, rollout: Rollout, region_name: str) -> RegionDisplayInfo:
        """Build region display info from rollout resource data."""
        status = "Not Started"
        start_time = None
        date = None

        for rg in rollout.resource_groups:
            if rg.location and rg.location.replace(" ", "").lower() == region_name.replace(" ", "").lower():
                for resource in rg.resources:
                    for action in resource.actions:
                        if action.status and action.status != "Succeeded":
                            status = action.status
                        elif action.status == "Succeeded" and status == "Not Started":
                            status = "Succeeded"
                        op = action.action_operation_info
                        if op:
                            if op.start_time and (start_time is None):
                                start_time = op.start_time
                            if op.end_time:
                                date = op.end_time
                            elif op.last_updated_time:
                                date = op.last_updated_time

        return RegionDisplayInfo(name=region_name, status=status, start_time=start_time, date=date)

    def _get_all_rollout_regions(self, rollout: Rollout) -> set[str]:
        """Collect all region names from rollout resource groups."""
        regions = set()
        for rg in rollout.resource_groups:
            if rg.location:
                regions.add(rg.location)
        return regions

    def _build_stages(self, rollout: Rollout) -> list[StageDisplayInfo]:
        """Build stage display info using configured stage definitions."""
        stages: list[StageDisplayInfo] = []
        assigned_regions: set[str] = set()
        all_regions = self._get_all_rollout_regions(rollout)

        for stage_cfg in self._config.stages:
            regions_for_stage: list[RegionDisplayInfo] = []

            if "REMAINING_REGIONS" in stage_cfg.regions:
                remaining = all_regions - assigned_regions
                for region_name in sorted(remaining):
                    regions_for_stage.append(self._build_region_info(rollout, region_name))
            else:
                for region_name in stage_cfg.regions:
                    regions_for_stage.append(self._build_region_info(rollout, region_name))
                    assigned_regions.add(region_name)

            stages.append(StageDisplayInfo(name=stage_cfg.name, regions=regions_for_stage))

        # Normalize: if all other regions succeeded and one is CheckInProgress, mark it Succeeded
        self._normalize_check_in_progress(stages)
        return stages

    @staticmethod
    def _normalize_check_in_progress(stages: list[StageDisplayInfo]) -> None:
        """Mirrors the C# status normalization logic."""
        all_regions: list[RegionDisplayInfo] = []
        for stage in stages:
            all_regions.extend(stage.regions)

        non_check = [r for r in all_regions if r.status != "CheckInProgress"]
        if all(r.status == "Succeeded" for r in non_check if r.status != "Not Started"):
            for r in all_regions:
                if r.status == "CheckInProgress":
                    r.status = "Succeeded"

    def _build_rollout_url(self, rollout: Rollout, service_group: str) -> str:
        env = rollout.rollout_details.environment if rollout.rollout_details else ""
        sid = self._config.ev2_api.service_identifier
        return (
            f"https://ra.ev2portal.azure.net/#/rollouts/{env}/{sid}/{service_group}/{rollout.rollout_id}"
        )

    async def _build_rollout_display(self, raw_rollout: dict, service_group: str) -> RolloutDisplayInfo | None:
        """Fetch full rollout detail and build display info."""
        rollout_id = raw_rollout.get("rolloutId", "")
        if not rollout_id:
            return None

        detail_data = await self.get_rollout(rollout_id, service_group)
        rollout = self._parse_rollout(detail_data)
        stages = self._build_stages(rollout)
        build_version = rollout.rollout_details.build_version if rollout.rollout_details else ""
        start_time = ""
        if rollout.rollout_operation_info and rollout.rollout_operation_info.start_time:
            start_time = rollout.rollout_operation_info.start_time

        return RolloutDisplayInfo(
            id=rollout.rollout_id,
            status=rollout.status,
            start_time=start_time,
            build_version=build_version,
            url=self._build_rollout_url(rollout, service_group),
            stages=stages,
        )

    # ------------------------------------------------------------------
    # Public high-level methods (exposed as MCP tools)
    # ------------------------------------------------------------------

    async def get_service_groups(self) -> list[ServiceGroupDisplayInfo]:
        """Fetch all service groups with their recent rollouts — mirrors the main endpoint."""
        now = datetime.now(timezone.utc)
        start_from = now - timedelta(days=self._config.ev2_api.rollout_lookback_days)
        results: list[ServiceGroupDisplayInfo] = []

        for sg_name in self._config.service_groups:
            raw_rollouts = await self.list_rollouts(sg_name, start_from, now)
            rollouts: list[RolloutDisplayInfo] = []
            for raw in raw_rollouts:
                display = await self._build_rollout_display(raw, sg_name)
                if display:
                    rollouts.append(display)
            rollouts.sort(key=lambda r: r.start_time, reverse=True)
            results.append(ServiceGroupDisplayInfo(name=sg_name, rollouts=rollouts))

        return results

    async def get_rollouts_for_group(
        self, service_group: str, lookback_days: int | None = None,
    ) -> list[RolloutDisplayInfo]:
        """Fetch rollouts for a single service group."""
        days = lookback_days or self._config.ev2_api.rollout_lookback_days
        now = datetime.now(timezone.utc)
        start_from = now - timedelta(days=days)
        raw_rollouts = await self.list_rollouts(service_group, start_from, now)

        rollouts: list[RolloutDisplayInfo] = []
        for raw in raw_rollouts:
            display = await self._build_rollout_display(raw, service_group)
            if display:
                rollouts.append(display)
        rollouts.sort(key=lambda r: r.start_time, reverse=True)
        return rollouts

    async def get_rollout_detail(self, rollout_id: str, service_group: str) -> RolloutDisplayInfo | None:
        """Fetch full detail for a single rollout."""
        detail_data = await self.get_rollout(rollout_id, service_group)
        rollout = self._parse_rollout(detail_data)
        stages = self._build_stages(rollout)
        build_version = rollout.rollout_details.build_version if rollout.rollout_details else ""
        start_time = ""
        if rollout.rollout_operation_info and rollout.rollout_operation_info.start_time:
            start_time = rollout.rollout_operation_info.start_time

        return RolloutDisplayInfo(
            id=rollout.rollout_id,
            status=rollout.status,
            start_time=start_time,
            build_version=build_version,
            url=self._build_rollout_url(rollout, service_group),
            stages=stages,
        )
