# app/routers/simple_map_viewer.py
import os, io, json, time, threading, queue, typing as T
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

class PoseIn(BaseModel):
    x: float
    y: float
    theta: float | None = 0.0

router = APIRouter(prefix="/simple-map", tags=["SimpleMap"])

# --- 설정 ---
MAP_DIR   = os.getenv("MAP_DIR", "maps")
YAML_PATH = os.getenv("MAP_YAML", os.path.join(MAP_DIR, "map1.yaml"))
POSE_TOPIC = os.getenv("POSE_TOPIC", "robot/+/telemetry/location")

# --- map.yaml 읽기 ---
def _load_yaml():
    import yaml, json
    from pathlib import Path

    # 1) 트윈이 쓰는 CONFIG 먼저 확인
    BASE_DIR  = Path(__file__).resolve().parent.parent
    PUBLIC_DIR = BASE_DIR.parent / "public"
    CONFIG = PUBLIC_DIR / "map-config.json"

    yaml_path = None

    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
            active = cfg.get("active")
            profs  = (cfg.get("profiles") or {})
            if active and active in profs and "yaml" in profs[active]:
                # map-config.json의 yaml 경로는 public 기준 상대경로(예: "maps/xxx.yaml")
                yaml_rel = profs[active]["yaml"]
                yaml_path = PUBLIC_DIR / yaml_rel
        except Exception:
            pass

    # 2) CONFIG가 없거나 실패하면 기본값(MAP_YAML, MAP_DIR)로
    if yaml_path is None:
        yaml_path = Path(os.getenv("MAP_YAML", os.path.join(MAP_DIR, "map1.yaml")))

    if not yaml_path.exists():
        raise FileNotFoundError(f"map.yaml not found: {yaml_path}")

    y = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    img_rel = y["image"]                  # e.g. "xxx.pgm" or "xxx.png"
    res     = float(y["resolution"])
    origin  = y["origin"]                 # [x0, y0, yaw]

    # 이미지 경로: yaml 기준 상대경로일 수 있으니 resolve
    img_path = (yaml_path.parent / img_rel).resolve()
    if not img_path.exists():
        raise FileNotFoundError(f"map image not found: {img_path}")

    return str(img_path), res, origin


def _img_size(path: str):
    try:
        from PIL import Image
        im = Image.open(path)
        return im.size
    except Exception:
        return (1024, 768)

# --- MQTT 구독 (app.mqtt_bus 우선, 실패 시 paho) ---
_subs: T.List[queue.Queue] = []
_latest_pose: T.Dict[str, float] = {}

def _broadcast(msg: dict):
    bad=[]
    for q in _subs:
        try: q.put_nowait(msg)
        except: bad.append(q)
    for q in bad:
        if q in _subs: _subs.remove(q)

def _setup_mqtt():
    # 1) 기존 프로젝트 mqtt_bus 재사용 시도
    try:
        from app.mqtt_bus import mqtt_bus
        def _cb(topic: str, payload):
            try:
                if isinstance(payload, (bytes, str)):
                    payload = json.loads(payload)
                if {"x","y"} <= payload.keys():
                    global _latest_pose
                    _latest_pose = {
                        "x": float(payload["x"]),
                        "y": float(payload["y"]),
                        "theta": float(payload.get("theta", 0.0))
                    }
                    _broadcast({"type":"pose","data":_latest_pose})
            except: pass
        mqtt_bus.subscribe(POSE_TOPIC, _cb)   # 너희 mqtt_bus의 subscribe 이름에 맞추기
        return "mqtt_bus"
    except Exception:
        pass

    # 2) paho fallback
    try:
        import paho.mqtt.client as mqtt
        host = os.getenv("MQTT_HOST", "broker")
        port = int(os.getenv("MQTT_PORT", "1883"))
        user = os.getenv("MQTT_USER", "") or None
        pw   = os.getenv("MQTT_PASS", "") or None

        def _on_connect(c, u, f, rc):
            c.subscribe(POSE_TOPIC, qos=1)

        def _on_message(c, u, m):
            try:
                data = json.loads(m.payload.decode("utf-8"))
                if {"x","y"} <= data.keys():
                    global _latest_pose
                    _latest_pose = {
                        "x": float(data["x"]),
                        "y": float(data["y"]),
                        "theta": float(data.get("theta", 0.0))
                    }
                    _broadcast({"type":"pose","data":_latest_pose})
            except: pass

        c = mqtt.Client()
        if user and pw: c.username_pw_set(user, pw)
        c.on_connect = _on_connect
        c.on_message = _on_message
        c.connect(host, port, 60)
        threading.Thread(target=c.loop_forever, daemon=True).start()
        return "paho"
    except Exception:
        return "none"

_MQTT_MODE = _setup_mqtt()

# --- 엔드포인트들 ---

@router.get("", response_class=HTMLResponse)
def page():
    return HTML_MINIMAL

@router.get("/map-config.json")
def cfg():
    img_path, res, origin = _load_yaml()
    w, h = _img_size(img_path)
    return JSONResponse({
        "resolution": res,
        "origin": origin,
        "width_px": w,
        "height_px": h,
        "mqtt_mode": _MQTT_MODE
    })

@router.get("/image")
def image():
    img_path, *_ = _load_yaml()
    ext = os.path.splitext(img_path)[1].lower()
    # 브라우저가 PGM을 못 그리므로 PNG로 즉시 변환해 전달
    if ext in [".pgm", ".ppm", ".pbm"]:
        try:
            from PIL import Image
        except ImportError:
            raise HTTPException(500, "Pillow 필요(PGM 변환). 'pip install Pillow'")
        im = Image.open(img_path)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/png")
    else:
        # PNG/JPG 등은 그대로
        mt = "image/png" if ext == ".png" else "image/jpeg"
        return FileResponse(img_path, media_type=mt)

@router.get("/pose/stream")
def pose_stream():
    q = queue.Queue()
    _subs.append(q)
    def gen():
        if _latest_pose:
            yield f"data: {json.dumps({'type':'pose','data':_latest_pose})}\n\n"
        while True:
            data = q.get()
            yield f"data: {json.dumps(data)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/pose")
def update_pose(pose: PoseIn):
    global _latest_pose
    _latest_pose = {"x": pose.x, "y": pose.y, "theta": float(pose.theta or 0.0)}
    _broadcast({"type": "pose", "data": _latest_pose})
    return {"ok": True}

# --- 초미니 HTML (지도 + 빨간 점만) ---
HTML_MINIMAL = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Map & Dot</title>
    <style>
        html, body {
            height: 100%;
            margin: 0;
            background: #000;
        }

        #wrap {
            display: flex;
            height: 100%;
            align-items: center;
            justify-content: center;
        }

        canvas {
            image-rendering: pixelated;
            outline: none;
        }
    </style>
</head>
<body>
    <div id="wrap"><canvas id="cv"></canvas></div>

    <script>
        window.addEventListener('DOMContentLoaded', () => {
            (async function() {
                const cfg = await (await fetch("/simple-map/map-config.json")).json();

                const img = new Image();
                img.src = "/simple-map/image?v=" + Date.now();
                await img.decode();

                const cv = document.getElementById("cv");
                const ctx = cv.getContext("2d");
                cv.width = cfg.width_px;
                cv.height = cfg.height_px;

                // 선명도 설정
                ctx.imageSmoothingEnabled = false;

                // 화면 크기에 맞춰 CSS 스케일
                const fit = Math.min(window.innerWidth / cv.width, window.innerHeight / cv.height);
                cv.style.width = (cv.width * fit) + "px";
                cv.style.height = (cv.height * fit) + "px";

                // 픽셀 조회용 오프스크린
                const mapCv = document.createElement("canvas");
                mapCv.width = cv.width;
                mapCv.height = cv.height;
                const mapCtx = mapCv.getContext("2d");
                mapCtx.imageSmoothingEnabled = false;
                mapCtx.drawImage(img, 0, 0);
                const mapImg = mapCtx.getImageData(0, 0, cv.width, cv.height).data;

                // 초기 배경(지도)
                ctx.drawImage(img, 0, 0);

                const DOT_R = 1.5; // 점 반지름(px)
                const ARROW_LEN = 12; // 화살표 길이(px)
                const ARROW_W = 7; // 화살촉 폭(px)

                function worldToPixel(x, y) {
                    const px = (x - cfg.origin[0]) / cfg.resolution;
                    const py = cfg.height_px - ((y - cfg.origin[1]) / cfg.resolution);
                    return [px, py];
                }

                function inBounds(px, py) {
                    return px >= 0 && px < cv.width && py >= 0 && py < cv.height;
                }

                function isWall(px, py) {
                    px = Math.floor(px);
                    py = Math.floor(py);
                    if (!inBounds(px, py)) return true;
                    const idx = (py * cv.width + px) * 4;
                    const r = mapImg[idx],
                        g = mapImg[idx + 1],
                        b = mapImg[idx + 2];
                    const lum = (r + g + b) / 3;
                    return lum < 80; // 검정=벽 (원하면 임계값 조절)
                }

                let prevPx = null,
                    prevPy = null;

                function constrainToFree(px0, py0, px1, py1) {
                    if (px0 == null || py0 == null) {
                        if (!isWall(px1, py1)) return [px1, py1];
                        for (let r = 1; r <= 5; r++) {
                            for (let a = 0; a < 360; a += 10) {
                                const rx = px1 + r * Math.cos(a * Math.PI / 180);
                                const ry = py1 + r * Math.sin(a * Math.PI / 180);
                                if (!isWall(rx, ry)) return [rx, ry];
                            }
                        }
                        return [Math.min(Math.max(px1, 0), cv.width - 1), Math.min(Math.max(py1, 0), cv.height - 1)];
                    }
                    const dx = px1 - px0,
                        dy = py1 - py0;
                    const steps = Math.max(Math.abs(dx), Math.abs(dy)) | 0;
                    let last = [px0, py0];
                    for (let i = 1; i <= steps; i++) {
                        const t = i / steps,
                            sx = px0 + dx * t,
                            sy = py0 + dy * t;
                        if (!inBounds(sx, sy) || isWall(sx, sy)) break;
                        last = [sx, sy];
                    }
                    return last;
                }

                // 예쁜 화살표(삼각형) 그리기
                function drawArrowHead(px, py, theta) {
                    // 방향벡터
                    const ux = Math.cos(theta),
                        uy = Math.sin(theta);
                    // 화면 y는 아래로 증가 → y성분 부호 주의(라인에서 이미 보정했으니 여기서는 그대로 사용)
                    const tipX = px + ARROW_LEN * ux;
                    const tipY = py - ARROW_LEN * uy;

                    // 좌우 날개(법선)
                    const nx = -uy,
                        ny = ux;
                    const baseX = px + (ARROW_LEN * 0.55) * ux;
                    const baseY = py - (ARROW_LEN * 0.55) * uy;

                    const leftX = baseX + (ARROW_W / 2) * nx;
                    const leftY = baseY - (ARROW_W / 2) * ny;
                    const rightX = baseX - (ARROW_W / 2) * nx;
                    const rightY = baseY + (ARROW_W / 2) * ny;

                    ctx.beginPath();
                    ctx.moveTo(tipX, tipY);
                    ctx.lineTo(leftX, leftY);
                    ctx.lineTo(rightX, rightY);
                    ctx.closePath();
                    ctx.fillStyle = "#ff2a2a";
                    ctx.fill();
                    // 테두리로 또렷하게
                    ctx.lineWidth = 1;
                    ctx.strokeStyle = "#ffffff";
                    ctx.stroke();
                }

                function renderDot(x, y, theta) {
                    const [tx, ty] = worldToPixel(x, y);
                    ctx.drawImage(img, 0, 0);

                    // 범위 클램프
                    const cx = Math.min(Math.max(tx, 0), cv.width - 1);
                    const cy = Math.min(Math.max(ty, 0), cv.height - 1);
                    // 벽 앞에서 멈춤
                    const [px, py] = constrainToFree(prevPx, prevPy, cx, cy);

                    // 점(선명: 흰 외곽선 + 빨강 면)
                    ctx.beginPath();
                    ctx.arc(px, py, DOT_R, 0, Math.PI * 2);
                    ctx.fillStyle = "#ff2a2a";
                    ctx.fill();
                    ctx.lineWidth = 0;
                    ctx.strokeStyle = "#ffffff";
                    ctx.stroke();

                    // 방향(예쁜 화살표)
                    if (theta !== null && theta !== undefined) {
                        drawArrowHead(px, py, theta);
                    }

                    prevPx = px;
                    prevPy = py;
                }

                // SSE 수신
                const es = new EventSource("/simple-map/pose/stream");
                es.onmessage = (ev) => {
                    const msg = JSON.parse(ev.data);
                    if (msg.type === "pose" && msg.data) {
                        const {
                            x,
                            y,
                            theta = 0
                        } = msg.data;
                        renderDot(x, y, theta);
                    }
                };
            })();
        });
    </script>
</body>
</html>
"""


