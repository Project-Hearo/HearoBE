import time
import logging
time.sleep(3)

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from app.database import engine, Base
from app.ws import ws_manager
from app.map_generator import generate_wall_and_meta
from app.mqtt_bus import mqtt_bus

from app.routers import (
    auth_router,
    user_router,
    sound_event_router,
    push_notification_router,
    guardian_router,
    user_setting_router,
    guardian_user_setting_router,
    map_router,
    battery_router,
    pose_ws_router,
    call_router,
    health,
    slam,
    debug_pose,
)

from app.utils import redirect_with_ts



load_dotenv()

app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z"
)
app.include_router(health.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

# 라우터 등록
app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(guardian_router.router)
app.include_router(sound_event_router.router)
app.include_router(push_notification_router.router)
app.include_router(user_setting_router.router)
app.include_router(guardian_user_setting_router.router)
app.include_router(map_router.router)
app.include_router(call_router.router)
app.include_router(slam.router)
app.include_router(battery_router.router)
app.include_router(pose_ws_router.router)
app.include_router(debug_pose.router)

# 경로 설정
APP_DIR = Path(__file__).resolve().parent
PROJ_DIR = APP_DIR.parent
PUBLIC_DIR = PROJ_DIR / "public"
FRONTEND_DIR = PROJ_DIR / "frontend" / "build"

def _nocache_headers(p: Path) -> dict:
    st = p.stat()
    etag = f'W/"{st.st_mtime_ns}-{st.st_size}"'
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, no-transform",
        "Pragma": "no-cache",
        "Expires": "0",
        "Surrogate-Control": "no-store",
        "ETag": etag,
        'Clear-Site-Data': '"cache"',
    }

@app.get("/map-config.json")
def get_map_config(request: Request):
    p = PUBLIC_DIR / "map-config.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    r = redirect_with_ts(request, p)
    if r:
        return r
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="application/json",
        headers=_nocache_headers(p),
    )

@app.get("/wall_shell.json")
def get_wall_shell(request: Request):
    p = PUBLIC_DIR / "wall_shell.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    r = redirect_with_ts(request, p)
    if r:
        return r
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="application/json",
        headers=_nocache_headers(p),
    )

@app.get("/meta.json")
def get_meta(request: Request):
    p = PUBLIC_DIR / "meta.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    r = redirect_with_ts(request, p)
    if r:
        return r
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="application/json",
        headers=_nocache_headers(p),
    )

@app.get("/obstacles.json")
def get_obstacles(request: Request):
    p = PUBLIC_DIR / "obstacles.json"
    if not p.exists():
        raise HTTPException(404, detail=f"{p} not found")
    r = redirect_with_ts(request, p)
    if r:
        return r
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="application/json",
        headers=_nocache_headers(p),
    )

@app.get("/service-worker.js")
def kill_service_worker():
    return Response(
        "/* Service Worker disabled by server */",
        status_code=410,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )

def _index_ts() -> int:
    idx = FRONTEND_DIR / "index.html"
    try:
        return int(idx.stat().st_mtime)
    except FileNotFoundError:
        return int(time.time())

@app.get("/")
def _root_redirect_or_serve(request: Request):
    q = dict(parse_qsl(request.url.query))
    if "ts" not in q:
        q["ts"] = str(_index_ts())
        parsed = urlparse(str(request.url))
        new_url = urlunparse(parsed._replace(query=urlencode(q)))
        return RedirectResponse(new_url, status_code=302)

    idx = FRONTEND_DIR / "index.html"
    if not idx.exists():
        raise HTTPException(404, detail=f"{idx} not found")
    return FileResponse(
        path=str(idx),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, no-transform",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

(PUBLIC_DIR / "maps").mkdir(parents=True, exist_ok=True)
app.mount("/maps", StaticFiles(directory=str(PUBLIC_DIR / "maps"), html=False), name="maps")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/_no_frontend")
    def _no_frontend():
        return {"ok": True, "msg": f"frontend not found at {FRONTEND_DIR}"}

@app.on_event("startup")
def _startup():
    # MQTT 브로커 연결
    async def _pose_sink(data: dict):
        await ws_manager.broadcast_json(data)
    mqtt_bus.set_pose_sink(_pose_sink)

    mqtt_bus.start()
    try:
        generate_wall_and_meta()
    except Exception as e:
        print("[Map Init Error]", e)
