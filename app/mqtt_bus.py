import json, os, uuid, threading, queue
from typing import Dict, Optional
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
    - 구독: app/+/resp/#, app/+/status/online
    - publish_cmd(): app/{robot_id}/cmd/{sub} 로 QoS1, retain False 발행
    - req_id -> Queue 로 스트리밍 라우팅, last_msg로 폴링도 지원
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

    def set_pose_sink(self, coro_fn):
        """coro_fn(data: dict) -> awaitable"""
        self.pose_sink = coro_fn

    # pose 전용 콜백 (req_id 필요 없음)
    def _on_pose_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            parts = msg.topic.split("/")
            robot_id = parts[1] if len(parts) >= 3 else "robot"

            x = float(data["x"])
            y = float(data["y"])
            theta = data.get("theta")  # optional


            payload = {
                "robot_id": robot_id,
                "x": x, "y": y,
                "theta": theta,  #라디안
            }

            if self.pose_sink:
                asyncio.run(self.pose_sink(payload))
            else:
                # 훅 미주입 시 직접 WS로
                from app.ws import ws_manager
                asyncio.run(ws_manager.broadcast_json(payload))

        except Exception as e:
            print(f"[mqtt_bus:pose] bad payload: {e}, raw={msg.payload!r}")

    def start(self):

        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe("app/+/resp/#", qos=1)
        client.subscribe("app/+/status/online", qos=1)

        client.subscribe("app/+/pose", qos=1)
        client.message_callback_add("app/+/pose", self._on_pose_message)

        client.subscribe("robot/+/telemetry/location", qos=1)
        client.message_callback_add("robot/+/telemetry/location", self._on_location_message)

        #client.subscribe("app/+/event/sound", qos=1)
        #client.message_callback_add("app/+/event/sound", self._on_sound_message)

    def _on_message(self, client, userdata, msg):
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

    def _on_location_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[mqtt_bus:location] bad json: {e}, raw={msg.payload!r}")
            return

        # robot/{robot_id}/telemetry/location
        parts = msg.topic.split("/")
        robot_id = parts[1] if len(parts) >= 4 else "robot"

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
        info = self.client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            qos=1, retain=False
        )

        return req_id  # 필요하면 topic도 함께 리턴하도록 바꿔도 OK


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
