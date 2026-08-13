from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodeCommandType(str, Enum):
    REBOOT = "REBOOT"
    UPDATE_SCHEDULE = "UPDATE_SCHEDULE"
    UPDATE_FIRMWARE = "UPDATE_FIRMWARE"
    CHANGE_MODE = "CHANGE_MODE"
    THROTTLE = "THROTTLE"
    EMERGENCY_UPLOAD = "EMERGENCY_UPLOAD"


class NodeRegister(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Unique node identifier assigned at provisioning")
    district: str = Field(..., description="Administrative district where the node is deployed")
    latitude: float = Field(..., description="Deployment latitude in decimal degrees")
    longitude: float = Field(..., description="Deployment longitude in decimal degrees")
    category: str = Field(..., description="Node category (e.g. ROAD, MARKET, BORDER)")
    hardware_profile: dict = Field(..., description="Hardware specifications (camera, SoC, storage)")
    network_config: dict = Field(..., description="Network configuration (LTE APN, proxy, etc.)")
    capture_schedule: str = Field(..., description="Cron-style capture schedule expression")
    interest_classes: list[str] = Field(..., description="Object classes the node should detect")
    pii_mode: str = Field(..., description="PII handling mode (e.g. REDACT_ON_DEVICE, UPLOAD_RAW)")
    firmware_version: str = Field(..., description="Current firmware version string")
    public_key: str = Field(..., description="Base64-encoded Ed25519 public key for authentication")


class NodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Server-assigned UUID for the node")
    node_id: str = Field(..., description="Unique node identifier")
    district: str = Field(..., description="Administrative district")
    latitude: float = Field(..., description="Deployment latitude")
    longitude: float = Field(..., description="Deployment longitude")
    category: str = Field(..., description="Node category")
    hardware_profile: dict = Field(..., description="Hardware specifications")
    network_config: dict = Field(..., description="Network configuration")
    capture_schedule: str = Field(..., description="Cron-style capture schedule")
    interest_classes: list[str] = Field(..., description="Object classes for detection")
    pii_mode: str = Field(..., description="PII handling mode")
    firmware_version: str = Field(..., description="Current firmware version")
    public_key: str = Field(..., description="Base64-encoded public key")
    status: str = Field(..., description="Current node status (ONLINE, OFFLINE, MAINTENANCE)")
    last_heartbeat_at: datetime | None = Field(default=None, description="Timestamp of last received heartbeat")
    is_enabled: bool = Field(..., description="Whether the node is administratively enabled")
    created_at: datetime = Field(..., description="Registration timestamp")


class HeartbeatPayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    battery_voltage: float = Field(..., description="Current battery voltage in volts")
    solar_input_watts: float = Field(..., description="Solar panel input power in watts")
    cpu_temp_celsius: float = Field(..., description="CPU temperature in degrees Celsius")
    gpu_utilization: float = Field(..., description="GPU utilization percentage (0-100)")
    storage_used_gb: float = Field(..., description="Storage used in gigabytes")
    storage_total_gb: float = Field(..., description="Total storage capacity in gigabytes")
    lte_rssi_dbm: float = Field(..., description="LTE signal strength in dBm")
    camera_status: str = Field(..., description="Camera status (OK, DEGRADED, OFFLINE)")
    clock_drift_ms: float = Field(..., description="Clock drift from NTP server in milliseconds")
    events_captured: int = Field(default=0, description="Number of events captured since last heartbeat")
    events_uploaded: int = Field(default=0, description="Number of events uploaded since last heartbeat")
    bandwidth_mbps: float = Field(default=0.0, description="Current bandwidth in megabits per second")
    raw_diagnostics: dict = Field(default_factory=dict, description="Additional vendor-specific diagnostics")


class HeartbeatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    received: bool = Field(..., description="Whether the heartbeat was successfully received")
    alerts: list[str] = Field(default_factory=list, description="Alerts triggered by server-side analysis")
    commands: list[dict] = Field(default_factory=list, description="Piggybacked commands for the node to execute")


class NodeCommand(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command: NodeCommandType = Field(..., description="Command type to execute on the node")
    payload: dict = Field(default_factory=dict, description="Command-specific parameters")


class NodeStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str = Field(..., description="Node identifier")
    status: str = Field(..., description="Current status (ONLINE, OFFLINE, MAINTENANCE)")
    battery_pct: float = Field(..., description="Battery level as percentage (0-100)")
    storage_pct: float = Field(..., description="Storage utilization as percentage (0-100)")
    last_sync: datetime | None = Field(default=None, description="Timestamp of last successful sync")
    district: str = Field(..., description="Administrative district")
    category: str = Field(..., description="Node category")
