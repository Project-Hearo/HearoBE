from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

from app.ws import ws_manager

router = APIRouter(prefix="/debug", tags=["Debug"])

class InjectPoseReq(BaseModel):
    x: float = Field(..., description="world X (meters)")
    y: float = Field(..., description="world Y (meters)")
    theta: Optional[float] = Field(None, description="yaw (radians)")
    frame: str = Field("map", description='"map" or "slam"')
    robot_id: str = Field("robot001", description="robot id (for UI grouping)")

@router.post("/inject-pose")
async def inject_pose(req: InjectPoseReq):
    frame = req.frame.lower()
    if frame not in ("map", "slam"):
        raise HTTPException(status_code=400, detail='frame must be "map" or "slam"')

    payload = {
        "robot_id": req.robot_id,
        "x": float(req.x),
        "y": float(req.y),
        **({"theta": float(req.theta)} if req.theta is not None else {}),
        "frame": frame,
    }

    await ws_manager.broadcast_json(payload)
    return {"ok": True, "sent": payload}
