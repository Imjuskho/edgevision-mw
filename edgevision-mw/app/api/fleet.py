from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_node_auth
from app.core.features import require_feature
from app.schemas.node import (
    HeartbeatPayload,
    HeartbeatResponse,
    NodeCommand,
)
from app.services.fleet import (
    get_active_alerts,
    get_fleet_status,
    get_node_detail,
    get_telemetry,
    record_heartbeat,
    send_node_command,
)

fleet_router = APIRouter(prefix="/nodes", tags=["Fleet"])


@fleet_router.post("/heartbeat", response_model=HeartbeatResponse)
async def node_heartbeat(
    payload: HeartbeatPayload,
    node_auth: dict = Depends(require_node_auth),
    db: AsyncSession = Depends(get_db),
):
    node_id = UUID(node_auth["node_id"])
    response = await record_heartbeat(db, node_id, payload)
    return response


@fleet_router.get("/")
async def list_nodes(
    district: str | None = Query(default=None, description="Filter by district"),
    category: str | None = Query(default=None, description="Filter by category"),
    node_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    user: dict = Depends(require_feature("fleet")),
    db: AsyncSession = Depends(get_db),
):
    filters = {}
    if district:
        filters["district"] = district
    if category:
        filters["category"] = category
    if node_status:
        filters["status"] = node_status
    return await get_fleet_status(db, filters or None, limit=limit, offset=offset)


@fleet_router.get("/alerts")
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    user: dict = Depends(require_feature("fleet")),
    db: AsyncSession = Depends(get_db),
):
    return await get_active_alerts(db, limit=limit, offset=offset)


@fleet_router.get("/{node_id}")
async def get_node(
    node_id: str,
    user: dict = Depends(require_feature("fleet")),
    db: AsyncSession = Depends(get_db),
):
    detail = await get_node_detail(db, node_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    return {
        "node": {
            "id": str(detail["node"].id),
            "node_id": detail["node"].node_id,
            "district": detail["node"].district,
            "status": detail["node"].status.value if hasattr(detail["node"].status, "value") else detail["node"].status,
            "last_heartbeat_at": detail["node"].last_heartbeat_at.isoformat()
            if detail["node"].last_heartbeat_at
            else None,
        },
        "recent_heartbeats": [
            {
                "timestamp": hb.created_at.isoformat(),
                "battery_voltage": hb.battery_voltage,
                "cpu_temp_celsius": hb.cpu_temp_celsius,
            }
            for hb in detail["recent_heartbeats"]
        ],
    }


@fleet_router.post("/{node_id}/command", status_code=status.HTTP_202_ACCEPTED)
async def post_command(
    node_id: str,
    command: NodeCommand,
    user: dict = Depends(require_feature("fleet")),
    db: AsyncSession = Depends(get_db),
):
    success = await send_node_command(db, node_id, command.model_dump())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    return {"message": "Command queued for next heartbeat", "node_id": str(node_id)}


@fleet_router.get("/{node_id}/telemetry")
async def node_telemetry(
    node_id: str,
    hours: int = Query(default=24, ge=1, le=168, description="Hours of telemetry"),
    user: dict = Depends(require_feature("fleet")),
    db: AsyncSession = Depends(get_db),
):
    telemetry = await get_telemetry(db, node_id, hours)
    return {"node_id": str(node_id), "hours": hours, "data_points": telemetry}
