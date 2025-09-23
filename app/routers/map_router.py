from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import asyncio, shutil, json

from app.map_generator import generate_wall_and_meta

router = APIRouter(prefix="/map", tags=["Map"])

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR.parent / "public"
MAPS_DIR = PUBLIC_DIR / "maps"
WALL_FILE = PUBLIC_DIR / "wall_shell.json"
META_FILE = PUBLIC_DIR / "meta.json"
CONFIG    = PUBLIC_DIR / "map-config.json"

clients: set[WebSocket] = set()

async def broadcast_json(msg: dict, exclude: WebSocket | None = None):
    dead = []
    data = json.dumps(msg)
    for ws in list(clients):
        if exclude is not None and ws is exclude:
            continue
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    print(f"[ws] client connected ({len(clients)})")
    try:
        while True:
            # 로봇/클라이언트가 보낸 메시지 수신
            msg = await ws.receive_text()
            try:
                obj = json.loads(msg)
            except Exception:
                continue

            if isinstance(obj, dict) and \
               isinstance(obj.get("x"), (int, float)) and \
               isinstance(obj.get("y"), (int, float)):
                await broadcast_json({"x": float(obj["x"]), "y": float(obj["y"])}, exclude=ws)
                continue

    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
        print(f"[ws] client disconnected ({len(clients)})")

@router.get("/wall")
async def get_wall():
    if not WALL_FILE.exists():
        return JSONResponse({"error": "wall_shell.json not found"}, status_code=404)
    return FileResponse(WALL_FILE)

@router.get("/meta")
async def get_meta():
    if not META_FILE.exists():
        return JSONResponse({"error": "meta.json not found"}, status_code=404)
    return FileResponse(META_FILE)

@router.post("/upload")
async def upload_map(yaml: UploadFile = File(...), pgm: UploadFile = File(...)):
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    yaml_path = MAPS_DIR / yaml.filename
    pgm_path = MAPS_DIR / pgm.filename

    with open(yaml_path, "wb") as f:
        shutil.copyfileobj(yaml.file, f)
    with open(pgm_path, "wb") as f:
        shutil.copyfileobj(pgm.file, f)

    cfg = {
        "active": "latest",
        "profiles": {
            "latest": {
                "yaml": f"maps/{yaml.filename}"
            }
        }
    }
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        generate_wall_and_meta()
    except Exception as e:
        return JSONResponse({"error": f"map generation failed: {e}"}, status_code=500)

    await broadcast_json({"event": "map_updated"})

    return {"ok": True, "yaml": str(yaml_path), "pgm": str(pgm_path)}
