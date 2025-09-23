from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Any, List

from app.schemas import BatteryReport

router = APIRouter(prefix="/battery", tags=["Battery"])

MAX_HISTORY = 500
_history: Deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY)
_last: Dict[str, Any] = {}

_ws_clients: List[WebSocket] = []

@router.post("")
async def post_battery(rep: BatteryReport):
    data = rep.dict()
    if not data.get("ts"):
        data["ts"] = datetime.now(timezone.utc).isoformat()

    _history.append(data)
    _last.update(data)

    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json({"type": "battery", "data": data})
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass

    return {"level": data["level"]}

@router.get("/latest")
async def get_latest():
    if not _last:
        return JSONResponse({"error": "no battery data yet"}, status_code=404)
    return _last

@router.get("/history")
async def get_history(limit: int = 100):
    limit = max(1, min(limit, MAX_HISTORY))

    items = list(_history)[-limit:]
    return list(items)

@router.websocket("/ws")
async def ws_battery(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)

    if _last:
        await ws.send_json({"type": "battery", "data": _last})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass
