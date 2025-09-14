from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
import time, json

from app.mqtt_bus import mqtt_bus
from app.schemas import SlamStartReq, EnqueueResp

router = APIRouter(prefix="/robots", tags=["SLAM"])

# 1) SLAM 시작: HTTP -> MQTT Publish (동시 구독 모드라 별도 전환 없음)
@router.post("/{robot_id}/slam/start", response_model=EnqueueResp)
def slam_start(robot_id: str, req: SlamStartReq):
    req_id = mqtt_bus.publish_cmd(
        robot_id,
        "slam/start",
        {"request": req.dict()}
    )
    return EnqueueResp(req_id=req_id)

# 2) 실시간 스트림(SSE): MQTT resp -> HTTP
#    동시 구독 모드: success 여부와 관계없이 전환 호출 없음(이미 두 토픽 상시 구독)
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

                # 종료 조건
                data_block = msg.get("data") or {}
                success = data_block.get("success") is True
                failed  = (msg.get("ok") is False)

                if success or failed:
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

# 4) SLAM 종료/맵업로드 완료 수동 전환 API
#    동시 구독 모드에서는 전환이 의미 없으므로, 호환용으로 OK만 반환
@router.post("/{robot_id}/slam/finish")
def slam_finish(robot_id: str):
    return {
        "ok": True,
        "mode": "dual-subscribe",  # 고정
        "topic_slam": f"robot/{robot_id}/telemetry/location",
        "topic_map": f"robot/{robot_id}/telemetry/map/location",
    }
