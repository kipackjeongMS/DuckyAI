"""Release Dashboard MCP Server — exposes EV2 rollout data as MCP tools."""

from __future__ import annotations

import json
import sys

from mcp.server.fastmcp import FastMCP

from .auth import Ev2Auth
from .config import load_config
from .ev2_client import Ev2Client
from .models import rollout_to_dict, service_group_to_dict, stage_to_dict

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

_config = load_config()
_auth = Ev2Auth(
    client_id=_config.auth.client_id,
    authority=_config.auth.authority,
    scopes=[_config.ev2_api.scope],
)
_client = Ev2Client(_config, _auth)

mcp = FastMCP(
    "release-dashboard",
    instructions="EV2 Release Dashboard — query Azure AppConfig deployment rollout status",
)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_service_groups() -> str:
    """Get all Azure AppConfig service groups with their recent rollouts (past 21 days).

    Returns a JSON array of service groups, each containing rollouts with
    stages and per-region deployment status. This is the primary dashboard view.
    """
    groups = await _client.get_service_groups()
    return json.dumps([service_group_to_dict(g) for g in groups], indent=2)


@mcp.tool()
async def get_rollouts(service_group: str, lookback_days: int = 21) -> str:
    """Get rollouts for a specific service group.

    Args:
        service_group: Full service group name (e.g. "Microsoft.Azure.AppConfiguration.AppConfigService").
                       Use get_service_groups to see all available names.
        lookback_days: Number of days to look back (default: 21).

    Returns JSON array of rollouts with stages and region statuses.
    """
    available = _config.service_groups
    if service_group not in available:
        return json.dumps({
            "error": f"Unknown service group: {service_group}",
            "available": available,
        })

    rollouts = await _client.get_rollouts_for_group(service_group, lookback_days)
    return json.dumps([rollout_to_dict(r) for r in rollouts], indent=2)


@mcp.tool()
async def get_rollout_details(rollout_id: str, service_group: str) -> str:
    """Get full details for a specific rollout including all stages and region statuses.

    Args:
        rollout_id: The rollout ID (UUID).
        service_group: The service group name this rollout belongs to.

    Returns JSON object with rollout details, stages, and per-region status.
    """
    detail = await _client.get_rollout_detail(rollout_id, service_group)
    if not detail:
        return json.dumps({"error": f"Rollout {rollout_id} not found"})
    return json.dumps(rollout_to_dict(detail), indent=2)


@mcp.tool()
async def get_stage_status(stage_name: str = "") -> str:
    """Get a summary of deployment status across all service groups for a given stage.

    Args:
        stage_name: Stage name to filter (e.g. "Stage 1", "Stage 2"). Leave empty for all stages.

    Returns a JSON summary with per-service-group stage/region statuses.
    """
    groups = await _client.get_service_groups()
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
