from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Any, List

from app.schemas import BatteryReport

router = APIRouter(prefix="/battery", tags=["Battery"])

# 최근 기록 N개 저장(메모리)
MAX_HISTORY = 500
_history: Deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY)
_last: Dict[str, Any] = {}

# 연결된 WS 클라이언트
_ws_clients: List[WebSocket] = []

@router.post("")
async def post_battery(rep: BatteryReport):
    data = rep.dict()
    if not data.get("ts"):
        data["ts"] = datetime.now(timezone.utc).isoformat()

    _history.append(data)
    _last.update(data)

    # 실시간 브로드캐스트(선택)
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

    return {"ok": True}

@router.get("/latest")
async def get_latest():
    if not _last:
        return JSONResponse({"error": "no battery data yet"}, status_code=404)
    return _last

@router.get("/history")
async def get_history(limit: int = 100):
    limit = max(1, min(limit, MAX_HISTORY))
    # 최신순으로 반환
    items = list(_history)[-limit:]
    return list(items)

@router.websocket("/ws")
async def ws_battery(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    # 접속 즉시 마지막 상태 1회 송신
    if _last:
        await ws.send_json({"type": "battery", "data": _last})
    try:
        while True:
            await ws.receive_text()  # ping용
    except WebSocketDisconnect:
        pass
    finally:
        try:
            _ws_clients.remove(ws)
        except ValueError:
            pass
