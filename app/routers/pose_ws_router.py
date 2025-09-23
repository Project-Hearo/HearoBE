from fastapi import APIRouter, WebSocket
from app.ws import ws_manager

router = APIRouter(prefix="/pose", tags=["Pose WS"])

@router.websocket("/ws")
async def pose_ws(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        ws_manager.disconnect(ws)
