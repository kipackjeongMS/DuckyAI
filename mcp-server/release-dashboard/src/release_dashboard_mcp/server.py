"""Release Dashboard MCP Server — exposes EV2 rollout data as MCP tools."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .auth import AuthRequired, Ev2Auth
from .config import load_config
from .ev2_client import Ev2Client
from .models import rollout_to_dict, service_group_to_dict, stage_to_dict

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "release-dashboard.log"),
    ],
)
logger = logging.getLogger("release-dashboard")

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_config = load_config()
_auth = Ev2Auth(resource=_config.ev2_api.resource_id)
_client = Ev2Client(_config, _auth)

logger.info("Server initialized — %d service groups configured", len(_config.service_groups))

mcp = FastMCP(
    "release-dashboard",
    instructions="EV2 Release Dashboard — query Azure AppConfig deployment rollout status",
)


def _auth_error_response(e: AuthRequired) -> str:
    """Format AuthRequired as a user-friendly tool response."""
    logger.warning("Auth required: %s", e.detail)
    return json.dumps({
        "auth_required": True,
        "message": str(e),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_service_groups(lookback_days: int = 21, start_date: str = "", end_date: str = "") -> str:
    """Get all Azure AppConfig service groups with their recent rollouts.

    Args:
        lookback_days: Number of days to look back for rollouts (default: 21). Ignored if start_date is set.
        start_date: Start date in YYYY-MM-DD format (e.g. "2026-01-01"). Overrides lookback_days.
        end_date: End date in YYYY-MM-DD format (e.g. "2026-01-30"). Defaults to today.

    Returns a JSON array of service groups, each containing rollouts with
    stages and per-region deployment status. This is the primary dashboard view.
    """
    logger.info("get_service_groups called — lookback=%d start=%s end=%s", lookback_days, start_date, end_date)
    try:
        groups = await _client.get_service_groups(
            lookback_days=lookback_days,
            start_date=start_date or None,
            end_date=end_date or None,
        )
        logger.info("get_service_groups returned %d groups", len(groups))
        return json.dumps([service_group_to_dict(g) for g in groups], indent=2)
    except AuthRequired as e:
        return _auth_error_response(e)


@mcp.tool()
async def get_rollouts(service_group: str, lookback_days: int = 21, start_date: str = "", end_date: str = "") -> str:
    """Get rollouts for a specific service group.

    Args:
        service_group: Full service group name (e.g. "Microsoft.Azure.AppConfiguration.AppConfigService").
                       Use get_service_groups to see all available names.
        lookback_days: Number of days to look back (default: 21). Ignored if start_date is set.
        start_date: Start date in YYYY-MM-DD format (e.g. "2026-01-01"). Overrides lookback_days.
        end_date: End date in YYYY-MM-DD format (e.g. "2026-01-30"). Defaults to today.

    Returns JSON array of rollouts with stages and region statuses.
    """
    logger.info("get_rollouts called — sg=%s lookback=%d start=%s end=%s", service_group, lookback_days, start_date, end_date)
    available = _config.service_groups
    if service_group not in available:
        logger.warning("Unknown service group: %s", service_group)
        return json.dumps({
            "error": f"Unknown service group: {service_group}",
            "available": available,
        })

    try:
        rollouts = await _client.get_rollouts_for_group(
            service_group,
            lookback_days=lookback_days,
            start_date=start_date or None,
            end_date=end_date or None,
        )
        return json.dumps([rollout_to_dict(r) for r in rollouts], indent=2)
    except AuthRequired as e:
        return _auth_error_response(e)


@mcp.tool()
async def get_rollout_details(rollout_id: str, service_group: str) -> str:
    """Get full details for a specific rollout including all stages and region statuses.

    Args:
        rollout_id: The rollout ID (UUID).
        service_group: The service group name this rollout belongs to.

    Returns JSON object with rollout details, stages, and per-region status.
    """
    logger.info("get_rollout_details called — rollout=%s sg=%s", rollout_id, service_group)
    try:
        detail = await _client.get_rollout_detail(rollout_id, service_group)
        if not detail:
            return json.dumps({"error": f"Rollout {rollout_id} not found"})
        return json.dumps(rollout_to_dict(detail), indent=2)
    except AuthRequired as e:
        return _auth_error_response(e)


@mcp.tool()
async def get_stage_status(stage_name: str = "", lookback_days: int = 21, start_date: str = "", end_date: str = "") -> str:
    """Get a summary of deployment status across all service groups for a given stage.

    Args:
        stage_name: Stage name to filter (e.g. "Stage 1", "Stage 2"). Leave empty for all stages.
        lookback_days: Number of days to look back for rollouts (default: 21). Ignored if start_date is set.
        start_date: Start date in YYYY-MM-DD format (e.g. "2026-01-01"). Overrides lookback_days.
        end_date: End date in YYYY-MM-DD format (e.g. "2026-01-30"). Defaults to today.

    Returns a JSON summary with per-service-group stage/region statuses.
    """
    logger.info("get_stage_status called — stage=%s lookback=%d start=%s end=%s", stage_name, lookback_days, start_date, end_date)
    try:
        groups = await _client.get_service_groups(
            lookback_days=lookback_days,
            start_date=start_date or None,
            end_date=end_date or None,
        )
    except AuthRequired as e:
        return _auth_error_response(e)

    summary = []
    for group in groups:
        group_entry = {"service_group": group.name, "rollouts": []}
        for rollout in group.rollouts:
            stages = rollout.stages
            if stage_name:
                stages = [s for s in stages if s.name.lower() == stage_name.lower()]
            if stages:
                group_entry["rollouts"].append({
                    "rollout_id": rollout.id,
                    "status": rollout.status,
                    "build_version": rollout.build_version,
                    "start_time": rollout.start_time,
                    "stages": [stage_to_dict(s) for s in stages],
                })
        if group_entry["rollouts"]:
            summary.append(group_entry)

    return json.dumps(summary, indent=2)


@mcp.tool()
async def list_service_group_names() -> str:
    """List all configured service group names. Useful for discovering valid inputs to other tools."""
    return json.dumps(_config.service_groups, indent=2)


@mcp.tool()
async def list_stages() -> str:
    """List all configured deployment stages and their regions."""
    return json.dumps(
        [{"name": s.name, "regions": s.regions} for s in _config.stages],
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
