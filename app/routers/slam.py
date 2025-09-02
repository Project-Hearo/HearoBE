from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse, StreamingResponse
import time, json

from app.mqtt_bus import mqtt_bus
from app.schemas import SlamStartReq, EnqueueResp

router = APIRouter(prefix="/robots", tags=["SLAM"])

# 1) SLAM 시작: HTTP -> MQTT Publish
@router.post("/{robot_id}/slam/start", response_model=EnqueueResp, status_code=202)
def slam_start(robot_id: str = Path(...), req: SlamStartReq = Body(...)):
    req_id = mqtt_bus.publish_cmd(robot_id, "slam/start", {
        "request": {
            "session_id": req.session_id,
            "save_map": req.save_map,
            "map_name": req.map_name,
            "duration_sec": req.duration_sec
        }
    })
    return {"req_id": req_id}

# 2) 실시간 스트림(SSE): MQTT resp -> HTTP
@router.get("/{robot_id}/slam/stream/{req_id}")
def slam_stream(robot_id: str, req_id: str, timeout_sec: int = 600):
    q = mqtt_bus.create_stream(req_id)

    def event_stream():
        start = time.time()
        accepted_deadline = start + 30  # 30초 내 accepted 없으면 에러 push
        try:
            while True:
                remain = max(0.05, accepted_deadline - time.time())
                if remain <= 0:
                    yield "data: " + json.dumps({
                        "req_id": req_id,
                        "ok": False,
                        "error": {"code": "no_action", "message": "no accepted within 30s"},
                        "ts": int(time.time()*1000)
                    }) + "\n\n"
                    return
                try:
                    msg = q.get(timeout=remain)
                except Exception:
                    continue

                # 들어온 메시지를 그대로 전달
                yield "data: " + json.dumps(msg, ensure_ascii=False) + "\n\n"

                # 종료 조건
                if (msg.get("data") or {}).get("success") is True or msg.get("ok") is False:
                    return

                if time.time() - start > timeout_sec:
                    yield "data: " + json.dumps({
                        "req_id": req_id,
                        "ok": False,
                        "error": {"code": "timeout", "message": "stream timeout"},
                        "ts": int(time.time()*1000)
                    }) + "\n\n"
                    return
        finally:
            mqtt_bus.close_stream(req_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 3) (옵션) 최근 상태 폴링 - 사용안해도됨
@router.get("/{robot_id}/slam/status/{req_id}")
def slam_status(robot_id: str, req_id: str):
    last = mqtt_bus.get_last(req_id)
    if not last:
        return JSONResponse(status_code=204, content=None)
    return last
