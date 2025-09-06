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
        self.client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        threading.Thread(target=self.client.loop_forever, daemon=True).start()

    def _on_connect(self, client, userdata, flags, rc):
        client.subscribe("app/+/resp/#", qos=1)
        client.subscribe("app/+/status/online", qos=1)

        client.subscribe("app/+/pose", qos=1)
        client.message_callback_add("app/+/pose", self._on_pose_message)

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
        req_id = request_dict.get("req_id") or uuid.uuid4().hex
        payload = {
            "req_id": req_id,
            "request": request_dict["request"],
        }
        self.client.publish(
            app_cmd_topic(rid, subtopic),
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            qos=1, retain=False
        )
        return req_id

mqtt_bus = MqttBus()
