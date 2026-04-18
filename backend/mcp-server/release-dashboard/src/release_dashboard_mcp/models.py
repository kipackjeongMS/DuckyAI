"""Data models for EV2 Release Dashboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# --- Display models (returned to MCP clients) ---

@dataclass
class RegionDisplayInfo:
    name: str
    status: str
    start_time: Optional[str] = None
    date: Optional[str] = None


@dataclass
class StageDisplayInfo:
    name: str
    regions: list[RegionDisplayInfo] = field(default_factory=list)


@dataclass
class RolloutDisplayInfo:
    id: str
    status: str
    start_time: str
    build_version: str
    url: str
    stages: list[StageDisplayInfo] = field(default_factory=list)


@dataclass
class ServiceGroupDisplayInfo:
    name: str
    rollouts: list[RolloutDisplayInfo] = field(default_factory=list)


# --- EV2 API response models ---

@dataclass
class ErrorInfo:
    status_code: int = 0
    error_code: str = ""
    error_reason: str = ""
    help_link: str = ""
    incident_link: str = ""
    escalate_to: str = ""
    escalate_info: str = ""


@dataclass
class ActionOperationInfo:
    correlation_id: str = ""
    deployment_name: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    last_updated_time: Optional[str] = None
    error_info: Optional[ErrorInfo] = None


@dataclass
class ResourceOperation:
    resource_name: str = ""
    resource_type: str = ""
    provisioning_state: str = ""
    status_message: str = ""
    status_code: str = ""
    mode: str = ""


@dataclass
class ActionDetail:
    name: str = ""
    step_name: str = ""
    status: str = ""
    action_operation_info: Optional[ActionOperationInfo] = None
    resource_operations: list[ResourceOperation] = field(default_factory=list)


@dataclass
class ResourceDetail:
    name: str = ""
    location: str = ""
    actions: list[ActionDetail] = field(default_factory=list)


@dataclass
class RolloutResourceGroup:
    name: str = ""
    azure_resource_group_name: str = ""
    location: str = ""
    last_updated_time: Optional[str] = None
    subscription_id: str = ""
    resources: list[ResourceDetail] = field(default_factory=list)


@dataclass
class RolloutDetails:
    service_group: str = ""
    environment: str = ""
    build_version: str = ""


@dataclass
class RolloutOperationInfo:
    retry_attempt: int = 0
    skip_succeeded_on_retry: bool = False
    start_time: Optional[str] = None


@dataclass
class Rollout:
    rollout_id: str = ""
    status: str = ""
    rollout_details: Optional[RolloutDetails] = None
    rollout_operation_info: Optional[RolloutOperationInfo] = None
    resource_groups: list[RolloutResourceGroup] = field(default_factory=list)


# --- Serialization helpers ---

def region_to_dict(r: RegionDisplayInfo) -> dict:
    return {"name": r.name, "status": r.status, "start_time": r.start_time, "date": r.date}

def stage_to_dict(s: StageDisplayInfo) -> dict:
    return {"name": s.name, "regions": [region_to_dict(r) for r in s.regions]}

def rollout_to_dict(r: RolloutDisplayInfo) -> dict:
    return {
        "id": r.id, "status": r.status, "start_time": r.start_time,
        "build_version": r.build_version, "url": r.url,
        "stages": [stage_to_dict(s) for s in r.stages],
    }

def service_group_to_dict(sg: ServiceGroupDisplayInfo) -> dict:
    return {"name": sg.name, "rollouts": [rollout_to_dict(r) for r in sg.rollouts]}
