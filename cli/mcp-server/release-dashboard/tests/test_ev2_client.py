"""Tests for Ev2Client — covers every public and internal method."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

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
    RolloutDisplayInfo,
    RolloutOperationInfo,
    RolloutResourceGroup,
    StageDisplayInfo,
)

# Import factories from conftest
from tests.conftest import _make_raw_rollout, _make_resource_group


# ===================================================================
# _get  (low-level HTTP helper)
# ===================================================================

class TestGet:
    """Tests for Ev2Client._get."""

    @pytest.mark.asyncio
    async def test_get_success(self, client):
        payload = {"value": [{"rolloutId": "r-1"}]}
        mock_resp = httpx.Response(200, json=payload, request=httpx.Request("GET", "https://ev2.test/api/rollouts"))

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client._get("/rollouts", {"api-version": "2016-07-01"})

        assert result == payload

    @pytest.mark.asyncio
    async def test_get_error_raises(self, client):
        mock_resp = httpx.Response(401, text="Unauthorized", request=httpx.Request("GET", "https://ev2.test/api/rollouts"))

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(RuntimeError, match="EV2 API error 401"):
                await client._get("/rollouts")

    @pytest.mark.asyncio
    async def test_get_includes_auth_header(self, client):
        mock_resp = httpx.Response(200, json={}, request=httpx.Request("GET", "https://ev2.test/api/test"))
        captured_kwargs = {}

        async def _capture(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_resp

        with patch("httpx.AsyncClient.get", side_effect=_capture):
            await client._get("/test")

        assert captured_kwargs["headers"]["Authorization"] == "Bearer fake-token"
        assert captured_kwargs["headers"]["Accept"] == "application/json"


# ===================================================================
# list_rollouts
# ===================================================================

class TestListRollouts:
    """Tests for Ev2Client.list_rollouts."""

    @pytest.mark.asyncio
    async def test_returns_list_when_api_returns_list(self, client):
        raw = [{"rolloutId": "r-1"}, {"rolloutId": "r-2"}]
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
            result = await client.list_rollouts("SG.Alpha", datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc))

        assert len(result) == 2
        assert result[0]["rolloutId"] == "r-1"

    @pytest.mark.asyncio
    async def test_returns_value_when_api_returns_dict(self, client):
        raw = {"value": [{"rolloutId": "r-3"}]}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
            result = await client.list_rollouts("SG.Alpha", datetime.now(timezone.utc), datetime.now(timezone.utc))

        assert len(result) == 1
        assert result[0]["rolloutId"] == "r-3"

    @pytest.mark.asyncio
    async def test_passes_correct_params(self, client):
        start = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end = datetime(2026, 3, 7, tzinfo=timezone.utc)

        with patch.object(client, "_get", new_callable=AsyncMock, return_value=[]) as mock_get:
            await client.list_rollouts("SG.Alpha", start, end)

        args, kwargs = mock_get.call_args
        # params passed as second positional arg
        params = kwargs.get("params") or args[1]
        assert params["servicegroupname"] == "SG.Alpha"
        assert "2026-03-01" in params["startTimeFrom"]
        assert "2026-03-07" in params["startTimeTo"]


# ===================================================================
# get_rollout
# ===================================================================

class TestGetRollout:
    """Tests for Ev2Client.get_rollout."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}) as mock_get:
            await client.get_rollout("r-42", "SG.Beta")

        mock_get.assert_awaited_once()
        args, kwargs = mock_get.call_args
        assert args[0] == "/rollouts/r-42"
        params = kwargs.get("params") or args[1]
        assert params["servicegroupname"] == "SG.Beta"
        assert params["embed-detail"] == "true"


# ===================================================================
# _parse_error_info  (static)
# ===================================================================

class TestParseErrorInfo:
    """Tests for Ev2Client._parse_error_info."""

    def test_returns_none_for_none(self):
        assert Ev2Client._parse_error_info(None) is None

    def test_returns_none_for_empty_dict(self):
        assert Ev2Client._parse_error_info({}) is None

    def test_parses_full_error(self):
        raw = {
            "statusCode": 500,
            "errorCode": "DeploymentFailed",
            "errorReason": "timeout",
            "helpLink": "https://help",
            "incidentLink": "https://icm",
            "escalateTo": "team-x",
            "escalateInfo": "urgent",
        }
        err = Ev2Client._parse_error_info(raw)
        assert err.status_code == 500
        assert err.error_code == "DeploymentFailed"
        assert err.error_reason == "timeout"
        assert err.help_link == "https://help"
        assert err.incident_link == "https://icm"
        assert err.escalate_to == "team-x"
        assert err.escalate_info == "urgent"

    def test_defaults_for_missing_keys(self):
        err = Ev2Client._parse_error_info({"statusCode": 400})
        assert err.status_code == 400
        assert err.error_code == ""
        assert err.error_reason == ""


# ===================================================================
# _parse_action_op_info  (static)
# ===================================================================

class TestParseActionOpInfo:
    """Tests for Ev2Client._parse_action_op_info."""

    def test_returns_none_for_none(self):
        assert Ev2Client._parse_action_op_info(None) is None

    def test_returns_none_for_empty_dict(self):
        assert Ev2Client._parse_action_op_info({}) is None

    def test_parses_full_info(self):
        raw = {
            "correlationId": "corr-1",
            "deploymentName": "dep-1",
            "startTime": "2026-03-01T00:00:00Z",
            "endTime": "2026-03-01T01:00:00Z",
            "lastUpdatedTime": "2026-03-01T01:00:00Z",
            "errorInfo": {"statusCode": 500, "errorCode": "Fail"},
        }
        info = Ev2Client._parse_action_op_info(raw)
        assert info.correlation_id == "corr-1"
        assert info.deployment_name == "dep-1"
        assert info.start_time == "2026-03-01T00:00:00Z"
        assert info.end_time == "2026-03-01T01:00:00Z"
        assert info.error_info is not None
        assert info.error_info.status_code == 500

    def test_nested_error_info_none_when_absent(self):
        info = Ev2Client._parse_action_op_info({"correlationId": "c"})
        assert info.error_info is None


# ===================================================================
# _parse_rollout  (static)
# ===================================================================

class TestParseRollout:
    """Tests for Ev2Client._parse_rollout."""

    def test_minimal_rollout(self):
        raw = _make_raw_rollout()
        rollout = Ev2Client._parse_rollout(raw)

        assert rollout.rollout_id == "r-001"
        assert rollout.status == "Completed"
        assert rollout.rollout_details.service_group == "SG.Alpha"
        assert rollout.rollout_details.build_version == "1.2.3"
        assert rollout.rollout_operation_info.start_time == "2026-03-01T00:00:00Z"
        assert rollout.resource_groups == []

    def test_rollout_with_resource_groups(self):
        rg = _make_resource_group(location="eastus2euap")
        raw = _make_raw_rollout(resource_groups=[rg])
        rollout = Ev2Client._parse_rollout(raw)

        assert len(rollout.resource_groups) == 1
        assert rollout.resource_groups[0].location == "eastus2euap"
        assert len(rollout.resource_groups[0].resources) == 1
        assert len(rollout.resource_groups[0].resources[0].actions) == 1

        action = rollout.resource_groups[0].resources[0].actions[0]
        assert action.name == "Deploy"
        assert action.status == "Succeeded"
        assert action.action_operation_info.correlation_id == "corr-1"
        assert len(action.resource_operations) == 1
        assert action.resource_operations[0].provisioning_state == "Succeeded"

    def test_empty_sub_dicts(self):
        raw = {"rolloutId": "r-empty", "status": "Unknown"}
        rollout = Ev2Client._parse_rollout(raw)

        assert rollout.rollout_id == "r-empty"
        assert rollout.rollout_details.service_group == ""
        assert rollout.rollout_operation_info.retry_attempt == 0
        assert rollout.resource_groups == []


# ===================================================================
# _build_region_info
# ===================================================================

class TestBuildRegionInfo:
    """Tests for Ev2Client._build_region_info."""

    def _rollout_with_region(self, location: str, action_status: str, start: str | None = None, end: str | None = None) -> Rollout:
        return Rollout(
            rollout_id="r-1",
            status="Completed",
            resource_groups=[
                RolloutResourceGroup(
                    name="rg",
                    location=location,
                    resources=[
                        ResourceDetail(
                            name="res",
                            location=location,
                            actions=[
                                ActionDetail(
                                    name="Deploy",
                                    status=action_status,
                                    action_operation_info=ActionOperationInfo(
                                        start_time=start,
                                        end_time=end,
                                        last_updated_time=end,
                                    ),
                                )
                            ],
                        )
                    ],
                )
            ],
        )

    def test_region_succeeded(self, client):
        rollout = self._rollout_with_region("eastus2euap", "Succeeded", "2026-03-01T01:00:00Z", "2026-03-01T02:00:00Z")
        info = client._build_region_info(rollout, "eastus2euap")

        assert info.name == "eastus2euap"
        assert info.status == "Succeeded"
        assert info.start_time == "2026-03-01T01:00:00Z"
        assert info.date == "2026-03-01T02:00:00Z"

    def test_region_failed(self, client):
        rollout = self._rollout_with_region("canadacentral", "Failed")
        info = client._build_region_info(rollout, "canadacentral")

        assert info.status == "Failed"

    def test_region_not_found_returns_not_started(self, client):
        rollout = self._rollout_with_region("eastus2euap", "Succeeded")
        info = client._build_region_info(rollout, "nonexistent")

        assert info.status == "Not Started"
        assert info.start_time is None

    def test_case_insensitive_space_insensitive_matching(self, client):
        rollout = self._rollout_with_region("East US 2 EUAP", "Succeeded", "t1", "t2")
        info = client._build_region_info(rollout, "eastus2euap")

        assert info.status == "Succeeded"

    def test_last_updated_used_as_date_when_no_end_time(self, client):
        rollout = Rollout(
            rollout_id="r-1",
            status="InProgress",
            resource_groups=[
                RolloutResourceGroup(
                    name="rg",
                    location="eastus",
                    resources=[
                        ResourceDetail(
                            name="res",
                            location="eastus",
                            actions=[
                                ActionDetail(
                                    name="Deploy",
                                    status="InProgress",
                                    action_operation_info=ActionOperationInfo(
                                        start_time="t-start",
                                        end_time=None,
                                        last_updated_time="t-updated",
                                    ),
                                )
                            ],
                        )
                    ],
                )
            ],
        )
        info = client._build_region_info(rollout, "eastus")
        assert info.date == "t-updated"


# ===================================================================
# _get_all_rollout_regions
# ===================================================================

class TestGetAllRolloutRegions:
    """Tests for Ev2Client._get_all_rollout_regions."""

    def test_collects_unique_locations(self, client):
        rollout = Rollout(
            resource_groups=[
                RolloutResourceGroup(name="a", location="eastus"),
                RolloutResourceGroup(name="b", location="westus"),
                RolloutResourceGroup(name="c", location="eastus"),
            ]
        )
        regions = client._get_all_rollout_regions(rollout)
        assert regions == {"eastus", "westus"}

    def test_skips_empty_location(self, client):
        rollout = Rollout(
            resource_groups=[
                RolloutResourceGroup(name="a", location=""),
                RolloutResourceGroup(name="b", location="westus"),
            ]
        )
        regions = client._get_all_rollout_regions(rollout)
        assert regions == {"westus"}

    def test_empty_resource_groups(self, client):
        rollout = Rollout(resource_groups=[])
        assert client._get_all_rollout_regions(rollout) == set()


# ===================================================================
# _build_stages
# ===================================================================

class TestBuildStages:
    """Tests for Ev2Client._build_stages."""

    def test_maps_regions_to_configured_stages(self, client):
        rg1 = _make_resource_group(name="rg1", location="eastus2euap")
        rg2 = _make_resource_group(name="rg2", location="canadacentral")
        rg3 = _make_resource_group(name="rg3", location="francecentral")
        raw = _make_raw_rollout(resource_groups=[rg1, rg2, rg3])
        rollout = Ev2Client._parse_rollout(raw)

        stages = client._build_stages(rollout)

        assert len(stages) == 3
        assert stages[0].name == "Stage 1"
        assert [r.name for r in stages[0].regions] == ["eastus2euap"]
        assert stages[1].name == "Stage 2"
        assert {r.name for r in stages[1].regions} == {"canadacentral", "francecentral"}

    def test_remaining_regions_catch_all(self, client):
        rg1 = _make_resource_group(name="rg1", location="eastus2euap")
        rg_extra = _make_resource_group(name="rg-extra", location="australiaeast")
        raw = _make_raw_rollout(resource_groups=[rg1, rg_extra])
        rollout = Ev2Client._parse_rollout(raw)

        stages = client._build_stages(rollout)

        stage3_names = {r.name for r in stages[2].regions}
        assert "australiaeast" in stage3_names
        assert "eastus2euap" not in stage3_names


# ===================================================================
# _normalize_check_in_progress  (static)
# ===================================================================

class TestNormalizeCheckInProgress:
    """Tests for Ev2Client._normalize_check_in_progress."""

    def test_check_in_progress_becomes_succeeded_when_others_succeeded(self):
        stages = [
            StageDisplayInfo(name="S1", regions=[
                RegionDisplayInfo(name="r1", status="Succeeded"),
                RegionDisplayInfo(name="r2", status="Succeeded"),
            ]),
            StageDisplayInfo(name="S2", regions=[
                RegionDisplayInfo(name="r3", status="CheckInProgress"),
            ]),
        ]
        Ev2Client._normalize_check_in_progress(stages)

        assert stages[1].regions[0].status == "Succeeded"

    def test_no_normalization_when_other_status_present(self):
        stages = [
            StageDisplayInfo(name="S1", regions=[
                RegionDisplayInfo(name="r1", status="Succeeded"),
                RegionDisplayInfo(name="r2", status="Failed"),
            ]),
            StageDisplayInfo(name="S2", regions=[
                RegionDisplayInfo(name="r3", status="CheckInProgress"),
            ]),
        ]
        Ev2Client._normalize_check_in_progress(stages)

        assert stages[1].regions[0].status == "CheckInProgress"

    def test_not_started_regions_are_ignored(self):
        stages = [
            StageDisplayInfo(name="S1", regions=[
                RegionDisplayInfo(name="r1", status="Succeeded"),
                RegionDisplayInfo(name="r2", status="Not Started"),
            ]),
            StageDisplayInfo(name="S2", regions=[
                RegionDisplayInfo(name="r3", status="CheckInProgress"),
            ]),
        ]
        Ev2Client._normalize_check_in_progress(stages)

        assert stages[1].regions[0].status == "Succeeded"

    def test_empty_stages_no_error(self):
        Ev2Client._normalize_check_in_progress([])


# ===================================================================
# _resolve_time_range
# ===================================================================

class TestResolveTimeRange:
    """Tests for Ev2Client._resolve_time_range."""

    def test_defaults_to_config_lookback(self, client):
        start, end = client._resolve_time_range()
        delta = end - start
        assert 20 <= delta.days <= 21

    def test_lookback_days_override(self, client):
        start, end = client._resolve_time_range(lookback_days=7)
        delta = end - start
        assert 6 <= delta.days <= 7

    def test_explicit_start_date_overrides_lookback(self, client):
        start, end = client._resolve_time_range(lookback_days=7, start_date="2026-01-01")
        assert start.year == 2026
        assert start.month == 1
        assert start.day == 1

    def test_explicit_end_date(self, client):
        start, end = client._resolve_time_range(start_date="2026-01-01", end_date="2026-01-30")
        assert start.day == 1
        assert end.day == 30
        assert end.hour == 23
        assert end.minute == 59

    def test_start_date_only_end_defaults_to_now(self, client):
        start, end = client._resolve_time_range(start_date="2026-01-15")
        assert start.day == 15
        now = datetime.now(timezone.utc)
        assert (now - end).total_seconds() < 5

    def test_end_date_without_start_uses_lookback(self, client):
        start, end = client._resolve_time_range(lookback_days=10, end_date="2026-06-15")
        assert end.month == 6
        assert end.day == 15
        # start is 10 days before now (not before end_date), so just verify it's set
        now = datetime.now(timezone.utc)
        assert (now - start).days <= 11


# ===================================================================
# _build_rollout_url
# ===================================================================

class TestBuildRolloutUrl:
    """Tests for Ev2Client._build_rollout_url."""

    def test_url_format(self, client):
        rollout = Rollout(
            rollout_id="r-42",
            rollout_details=RolloutDetails(environment="Prod"),
        )
        url = client._build_rollout_url(rollout, "SG.Alpha")
        assert url == "https://ra.ev2portal.azure.net/#/rollouts/Prod/test-sid/SG.Alpha/r-42"

    def test_empty_environment(self, client):
        rollout = Rollout(rollout_id="r-1", rollout_details=RolloutDetails())
        url = client._build_rollout_url(rollout, "SG.Beta")
        assert "/rollouts//test-sid/SG.Beta/r-1" in url

    def test_no_rollout_details(self, client):
        rollout = Rollout(rollout_id="r-1", rollout_details=None)
        url = client._build_rollout_url(rollout, "SG.Alpha")
        assert "/rollouts//test-sid/SG.Alpha/r-1" in url


# ===================================================================
# _build_rollout_display
# ===================================================================

class TestBuildRolloutDisplay:
    """Tests for Ev2Client._build_rollout_display."""

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_rollout_id(self, client):
        result = await client._build_rollout_display({"rolloutId": ""}, "SG.Alpha")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_rollout_id(self, client):
        result = await client._build_rollout_display({}, "SG.Alpha")
        assert result is None

    @pytest.mark.asyncio
    async def test_builds_display_from_detail(self, client):
        detail = _make_raw_rollout(
            rollout_id="r-10",
            build_version="2.0.0",
            resource_groups=[_make_resource_group(location="eastus2euap")],
        )
        with patch.object(client, "get_rollout", new_callable=AsyncMock, return_value=detail):
            display = await client._build_rollout_display({"rolloutId": "r-10"}, "SG.Alpha")

        assert display is not None
        assert display.id == "r-10"
        assert display.build_version == "2.0.0"
        assert display.status == "Completed"
        assert len(display.stages) == 3
        assert "SG.Alpha" in display.url


# ===================================================================
# get_service_groups  (high-level)
# ===================================================================

class TestGetServiceGroups:
    """Tests for Ev2Client.get_service_groups."""

    @pytest.mark.asyncio
    async def test_returns_all_configured_groups(self, client):
        raw_rollout = _make_raw_rollout(rollout_id="r-1")
        detail = _make_raw_rollout(rollout_id="r-1", resource_groups=[_make_resource_group()])

        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=[raw_rollout]), \
             patch.object(client, "get_rollout", new_callable=AsyncMock, return_value=detail):
            groups = await client.get_service_groups()

        assert len(groups) == 2
        assert groups[0].name == "SG.Alpha"
        assert groups[1].name == "SG.Beta"

    @pytest.mark.asyncio
    async def test_empty_rollouts(self, client):
        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=[]):
            groups = await client.get_service_groups()

        assert all(len(g.rollouts) == 0 for g in groups)

    @pytest.mark.asyncio
    async def test_rollouts_sorted_descending_by_start_time(self, client):
        raw1 = {"rolloutId": "r-old"}
        raw2 = {"rolloutId": "r-new"}
        detail_old = _make_raw_rollout(rollout_id="r-old", start_time="2026-03-01T00:00:00Z")
        detail_new = _make_raw_rollout(rollout_id="r-new", start_time="2026-03-05T00:00:00Z")

        async def _get_rollout(rid, sg):
            return detail_new if rid == "r-new" else detail_old

        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=[raw1, raw2]), \
             patch.object(client, "get_rollout", side_effect=_get_rollout):
            groups = await client.get_service_groups()

        rollouts = groups[0].rollouts
        assert len(rollouts) == 2
        assert rollouts[0].id == "r-new"
        assert rollouts[1].id == "r-old"


# ===================================================================
# get_rollouts_for_group  (high-level)
# ===================================================================

class TestGetRolloutsForGroup:
    """Tests for Ev2Client.get_rollouts_for_group."""

    @pytest.mark.asyncio
    async def test_default_lookback(self, client):
        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=[]) as mock_list:
            await client.get_rollouts_for_group("SG.Alpha")

        args = mock_list.call_args[0]
        start_from, end = args[1], args[2]
        assert (end - start_from).days == 21

    @pytest.mark.asyncio
    async def test_custom_lookback(self, client):
        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=[]) as mock_list:
            await client.get_rollouts_for_group("SG.Alpha", lookback_days=7)

        args = mock_list.call_args[0]
        start_from, end = args[1], args[2]
        assert (end - start_from).days == 7

    @pytest.mark.asyncio
    async def test_returns_sorted_rollouts(self, client):
        raw = [{"rolloutId": "r-1"}, {"rolloutId": "r-2"}]
        d1 = _make_raw_rollout(rollout_id="r-1", start_time="2026-03-01T00:00:00Z")
        d2 = _make_raw_rollout(rollout_id="r-2", start_time="2026-03-03T00:00:00Z")

        async def _get_rollout(rid, sg):
            return d1 if rid == "r-1" else d2

        with patch.object(client, "list_rollouts", new_callable=AsyncMock, return_value=raw), \
             patch.object(client, "get_rollout", side_effect=_get_rollout):
            rollouts = await client.get_rollouts_for_group("SG.Alpha")

        assert rollouts[0].id == "r-2"
        assert rollouts[1].id == "r-1"


# ===================================================================
# get_rollout_detail  (high-level)
# ===================================================================

class TestGetRolloutDetail:
    """Tests for Ev2Client.get_rollout_detail."""

    @pytest.mark.asyncio
    async def test_returns_display_info(self, client):
        detail = _make_raw_rollout(
            rollout_id="r-99",
            build_version="9.9.9",
            resource_groups=[_make_resource_group(location="eastus2euap")],
        )
        with patch.object(client, "get_rollout", new_callable=AsyncMock, return_value=detail):
            result = await client.get_rollout_detail("r-99", "SG.Alpha")

        assert result.id == "r-99"
        assert result.build_version == "9.9.9"
        assert result.start_time == "2026-03-01T00:00:00Z"
        assert len(result.stages) == 3
        assert "r-99" in result.url

    @pytest.mark.asyncio
    async def test_missing_start_time_defaults_to_empty(self, client):
        raw = {
            "rolloutId": "r-no-time",
            "status": "Queued",
            "rolloutDetails": {"buildVersion": "0.0.1"},
            "rolloutOperationInfo": {},
        }
        with patch.object(client, "get_rollout", new_callable=AsyncMock, return_value=raw):
            result = await client.get_rollout_detail("r-no-time", "SG.Alpha")

        assert result.start_time == ""
