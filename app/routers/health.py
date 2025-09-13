from fastapi import APIRouter
from sqlalchemy import text
from app.database import engine
import os, socket

router = APIRouter(tags=["Health"])

@router.get("/healthz")
def healthz():

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/healthz/mqtt")
def healthz_mqtt():

    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    try:
        with socket.create_connection((host, port), timeout=2):
            return {"ok": True, "host": host, "port": port}
    except Exception as e:
        return {"ok": False, "host": host, "port": port, "error": str(e)}
