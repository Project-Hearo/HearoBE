from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
import time, json

from app.mqtt_bus import mqtt_bus
from app.schemas import SlamStartReq, EnqueueResp

router = APIRouter(prefix="/robots", tags=["SLAM"])

# 1) SLAM 시작: HTTP -> MQTT Publish + 구독 전환(location)
@router.post("/{robot_id}/slam/start", response_model=EnqueueResp)
def slam_start(robot_id: str, req: SlamStartReq):
    # SLAM 시작 시, 위치 토픽을 robot/{id}/telemetry/location 으로 전환
    try:
        mqtt_bus.switch_to_location(robot_id)
        print(f"[slam/start] switched to location for robot={robot_id}")
    except Exception as e:
        print(f"[slam/start] switch_to_location failed: {e}")

    req_id = mqtt_bus.publish_cmd(
        robot_id,
        "slam/start",
        {"request": req.dict()}
    )
    return EnqueueResp(req_id=req_id)

# 2) 실시간 스트림(SSE): MQTT resp -> HTTP
#    success=True 수신 시, robot/{id}/telemetry/map/location 으로 전환
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
                    }, ensure_ascii=False) + "\n\n"
                    return
                try:
                    msg = q.get(timeout=remain)
                except Exception:
                    continue

                # 들어온 메시지를 그대로 전달
                yield "data: " + json.dumps(msg, ensure_ascii=False) + "\n\n"

                # 종료/전환 조건
                data_block = msg.get("data") or {}
                success = data_block.get("success") is True
                failed  = (msg.get("ok") is False)

                if success:
                    # SLAM 성공적으로 끝났다면 robot/{id}/telemetry/map/location 으로 전환
                    try:
                        mqtt_bus.switch_to_map_location(robot_id)
                        print(f"[slam/stream] success -> switched to robot/{robot_id}/telemetry/map/location")
                    except Exception as e:
                        print("[slam/stream] switch_to_map_location failed:", e)
                    return

                if failed:
                    # 실패면 전환하지 않고 종료(여전히 location 모드 유지)
                    return

                # 타임아웃 처리
                if time.time() - start > timeout_sec:
                    yield "data: " + json.dumps({
                        "req_id": req_id,
                        "ok": False,
                        "error": {"code": "timeout", "message": "stream timeout"},
                        "ts": int(time.time()*1000)
                    }, ensure_ascii=False) + "\n\n"
                    return
        finally:
            mqtt_bus.close_stream(req_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# 3) 최근 상태 폴링 - 사용안해도됨
@router.get("/{robot_id}/slam/status/{req_id}")
def slam_status(robot_id: str, req_id: str):
    last = mqtt_bus.get_last(req_id)
    if not last:
        return JSONResponse(status_code=204, content=None)
    return last

# 4) SLAM 종료/맵업로드 완료 후 수동 전환 API
@router.post("/{robot_id}/slam/finish")
def slam_finish(robot_id: str):
    try:
        mqtt_bus.switch_to_map_location(robot_id)   # robot/{id}/telemetry/map/location
        print(f"[slam/finish] switched to robot/{robot_id}/telemetry/map/location")
        return {"ok": True, "mode": "map", "topic": f"robot/{robot_id}/telemetry/map/location"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
