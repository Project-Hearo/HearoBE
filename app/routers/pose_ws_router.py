from fastapi import APIRouter, WebSocket
from app.ws import ws_manager

router = APIRouter(prefix="/pose", tags=["Pose WS"])

@router.websocket("/ws")
async def pose_ws(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # 클라이언트가 아무것도 안 보내도 OK
    except Exception:
        pass
    finally:
        ws_manager.disconnect(ws)
