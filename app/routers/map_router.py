from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import asyncio
import shutil

# utils 안에 있는 함수 불러오기
from app.map_generator import generate_wall_and_meta

router = APIRouter(prefix="/map", tags=["Map"])

BASE_DIR = Path(__file__).resolve().parent.parent   # ./app
PUBLIC_DIR = BASE_DIR.parent / "public"
MAPS_DIR = PUBLIC_DIR / "maps"  # 업로드 지도 저장용 폴더
WALL_FILE = PUBLIC_DIR / "wall_shell.json"
META_FILE = PUBLIC_DIR / "meta.json"

clients = set()

# ================= 파일 반환 =================
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

# ================= Pose API =================
@router.post("/pose")
async def post_pose(pose: dict):
    """
    로봇이 좌표(x, y)를 보내면
    연결된 모든 WebSocket 클라이언트에게 전송
    """
    msg = {"x": float(pose["x"]), "y": float(pose["y"])}
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
    return {"ok": True}

# ================= WebSocket =================
@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    print(f"[ws] client connected ({len(clients)})")
    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
        print(f"[ws] client disconnected ({len(clients)})")

# ================= 지도 업로드 =================
@router.post("/upload")
async def upload_map(yaml: UploadFile = File(...), pgm: UploadFile = File(...)):
    """
    로봇이 map.yaml + map.pgm 파일을 업로드하면
    1) 서버에 저장
    2) slam_to_wall_shell_from_yaml 실행 (wall/meta.json 갱신)
    3) 모든 WebSocket 클라이언트에게 "map_updated" 알림
    """
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    yaml_path = MAPS_DIR / yaml.filename
    pgm_path = MAPS_DIR / pgm.filename

    with open(yaml_path, "wb") as f:
        shutil.copyfileobj(yaml.file, f)
    with open(pgm_path, "wb") as f:
        shutil.copyfileobj(pgm.file, f)

    # wall_shell.json + meta.json 재생성
    try:
        generate_wall_and_meta()
    except Exception as e:
        return JSONResponse({"error": f"map generation failed: {e}"}, status_code=500)

    # WebSocket 클라이언트에 알림
    msg = {"event": "map_updated"}
    dead = []
    for ws in list(clients):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

    return {"ok": True, "yaml": str(yaml_path), "pgm": str(pgm_path)}
