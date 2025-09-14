import json, os, uuid, threading, queue
from typing import Dict, Optional, Callable
import paho.mqtt.client as mqtt
import asyncio

MQTT_HOST = os.getenv("MQTT_HOST", "broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

DEFAULT_ROBOT_ID = os.getenv("ROBOT_ID", "robot001")

def app_cmd_topic(robot_id: str, sub: str) -> str:
    return f"app/{robot_id}/cmd/{sub}"

def _new_req_id() -> str:
    return f"REQ-{uuid.uuid4().hex}"

def app_resp_topic(robot_id: str, sub: str) -> str:
    return f"app/{robot_id}/resp/{sub}"

class MqttBus:
    """
    - 시작 구독: robot/+/telemetry/location  (SLAM 중)
    - 업로드 완료 시: switch_to_map_location(robot_id?) → robot/{robot_id}/telemetry/map/location
    - 공통: app/+/resp/#, app/+/status/online 구독 유지
    - publish_cmd(): app/{robot_id}/cmd/{sub} 로 QoS1, retain False 발행
    - req_id -> Queue 라우팅, last_msg 폴링 제공
    """
    def __init__(self):
        self.client = mqtt.Client(client_id=f"app-server-{uuid.uuid4().hex[:8]}")
        if MQTT_USER:
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self.streams: Dict[str, "queue.Queue[dict]"] = {}
        self.last_msg: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.pose_sink = None

        # ▼ 현재 "위치 스트림" 토픽/콜백 (초기값: SLAM location)
        self._pose_topic_filter: str = "robot/+/telemetry/location"
        self._pose_callback:    Callable = self._on_location_message

    def set_pose_sink(self, coro_fn):
        """coro_fn(data: dict) -> awaitable"""
        self.pose_sink = coro_fn

    # ---------- 시작/연결 ----------

    def start(self):
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def _on_connect(self, client, userdata, flags, rc):
        # 공통 응답/상태 구독
        client.subscribe("app/+/resp/#", qos=1)
        client.subscribe("app/+/status/online", qos=1)

        # 현재 설정된 위치 스트림 토픽만 구독
        client.subscribe(self._pose_topic_filter, qos=1)
        client.message_callback_add(self._pose_topic_filter, self._pose_callback)

    # ---------- 동적 전환 API ----------

    def switch_location_topic(self, topic_filter: str, callback: Optional[Callable] = None):
        """현재 위치 토픽을 동적으로 전환(언/구독 + 콜백 재바인딩)."""
        with self.lock:
            old_filter = self._pose_topic_filter
            old_cb     = self._pose_callback
            new_filter = topic_filter
            new_cb     = callback or self._on_location_message

            # 내부 상태 먼저 교체(재연결 시에도 새 설정 반영)
            self._pose_topic_filter = new_filter
            self._pose_callback     = new_cb

        # 이전 콜백 제거 + 언구독
        try:
            self.client.message_callback_remove(old_filter)
        except Exception:
            pass
        try:
            self.client.unsubscribe(old_filter)
        except Exception:
            pass

        # 새 토픽 구독 + 콜백 바인딩
        self.client.subscribe(new_filter, qos=1)
        self.client.message_callback_add(new_filter, new_cb)

        print(f"[mqtt_bus] location topic switched: {old_filter}  -->  {new_filter}")

    def switch_to_location(self, robot_id: Optional[str] = None):
        """
        SLAM 단계(기본 위치)로 복귀.
        robot_id 지정 시: robot/{robot_id}/telemetry/location
        미지정 시:       robot/+/telemetry/location
        """
        tf = f"robot/{robot_id}/telemetry/location" if robot_id else "robot/+/telemetry/location"
        self.switch_location_topic(tf, callback=self._on_location_message)

    def switch_to_map_location(self, robot_id: Optional[str] = None):
        """
        맵 모드(지도 좌표계)로 전환.
        robot_id 지정 시: robot/{robot_id}/telemetry/map/location
        미지정 시:       robot/+/telemetry/map/location
        """
        tf = f"robot/{robot_id}/telemetry/map/location" if robot_id \
             else "robot/+/telemetry/map/location"
        self.switch_location_topic(tf, callback=self._on_map_location_message)

    # ---------- 메시지/라우팅 ----------

    def _on_message(self, client, userdata, msg):
        # 공통 resp 라우팅 (req_id 기반)
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        req_id = str(payload.get("req_id") or "")
        if not req_id:
            return
        with self.lock:
            self.last_msg[req_id] = payload
            q = self.streams.get(req_id)
        if q:
            q.put(payload)

    # /telemetry/map/location 콜백 (지도 좌표계)
    def _on_map_location_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))

            # 토픽에서 robot_id 우선 추출
            parts = [p for p in msg.topic.split('/') if p]
            robot_id = None
            if len(parts) >= 5 and parts[0] == "robot":
                # robot/{id}/telemetry/map/location
                robot_id = parts[1]
            if not robot_id:
                robot_id = data.get("robot_id") or DEFAULT_ROBOT_ID

            # 다양한 형태를 허용
            norm = _normalize_location_payload(data)
            if not norm and all(k in data for k in ("x","y")):
                norm = {"x": float(data["x"]), "y": float(data["y"])}
                if isinstance(data.get("theta"), (int, float)):
                    norm["theta"] = float(data["theta"])
            if not norm:
                print(f"[mqtt_bus:map_location] bad payload: {data}")
                return

            payload = {"robot_id": robot_id, **norm}

            if self.pose_sink:
                asyncio.run(self.pose_sink(payload))
            else:
                from app.ws import ws_manager
                asyncio.run(ws_manager.broadcast_json(payload))
        except Exception as e:
            print(f"[mqtt_bus:map_location] error: {e}, raw={msg.payload!r}")

    # SLAM location 콜백 (기존)
    def _on_location_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[mqtt_bus:location] bad json: {e}, raw={msg.payload!r}")
            return

        # robot/{robot_id}/telemetry/location
        parts = [p for p in msg.topic.split('/') if p]
        robot_id = parts[1] if len(parts) >= 4 and parts[0] == "robot" else DEFAULT_ROBOT_ID

        norm = _normalize_location_payload(data)
        if not norm:
            print(f"[mqtt_bus:location] missing x/y in payload: {data}")
            return

        payload = {"robot_id": robot_id, **norm}  # {robot_id,x,y,theta?}

        if self.pose_sink:
            try:
                asyncio.run(self.pose_sink(payload))
                return
            except Exception as e:
                print("[mqtt_bus:location] pose_sink error:", e)

        try:
            from app.ws import ws_manager
            asyncio.run(ws_manager.broadcast_json(payload))
        except Exception as e:
            print("[mqtt_bus:location] ws broadcast error:", e)

    # ---------- 스트림/요청 유틸 ----------

    def create_stream(self, req_id: str):
        q: "queue.Queue[dict]" = queue.Queue()
        with self.lock:
            self.streams[req_id] = q
        return q

    def close_stream(self, req_id: str):
        with self.lock:
            self.streams.pop(req_id, None)

    def get_last(self, req_id: str) -> Optional[dict]:
        with self.lock:
            return self.last_msg.get(req_id)

    def publish_cmd(self, robot_id: Optional[str], subtopic: str, request_dict: dict) -> str:
        rid = robot_id or DEFAULT_ROBOT_ID

        # 항상 서버에서 req_id 생성(외부가 넣어줬다면 그걸 사용)
        req_id = (request_dict or {}).get("req_id") or _new_req_id()

        # request 블록 보정
        request_block = (request_dict or {}).get("request") or {}
        payload = {
            "req_id": req_id,
            "request": request_block,
        }

        topic = app_cmd_topic(rid, subtopic)
        self.client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            qos=1, retain=False
        )

        return req_id  # 필요하면 topic도 함께 리턴하도록 바꿔도 OK

# ---------- 보조 ----------

def _normalize_location_payload(raw: dict):
    x = y = theta = None
    if isinstance(raw.get("x"), (int, float)) and isinstance(raw.get("y"), (int, float)):
        x, y = float(raw["x"]), float(raw["y"])
        if isinstance(raw.get("theta"), (int, float)): theta = float(raw["theta"])
    elif isinstance(raw.get("pos"), dict):
        p = raw["pos"]
        if isinstance(p.get("x"), (int, float)) and isinstance(p.get("y"), (int, float)):
            x, y = float(p["x"]), float(p["y"])
        if isinstance(raw.get("yaw"), (int, float)): theta = float(raw["yaw"])
    elif isinstance(raw.get("position"), (list, tuple)) and len(raw["position"]) >= 2:
        x, y = float(raw["position"][0]), float(raw["position"][1])
        if len(raw["position"]) >= 3 and isinstance(raw["position"][2], (int, float)):
            theta = float(raw["position"][2])
    if x is None or y is None:
        return None
    return {"x": x, "y": y, **({"theta": theta} if theta is not None else {})}

mqtt_bus = MqttBus()
