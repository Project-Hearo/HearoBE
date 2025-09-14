import bcrypt

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

from pathlib import Path
from fastapi import Request
from urllib.parse import urlencode, urlunparse, urlparse, parse_qsl
from fastapi.responses import RedirectResponse
import time

def file_mtime_ts(p: Path) -> int:
    try:
        return int(p.stat().st_mtime)
    except FileNotFoundError:
        return int(time.time())

def redirect_with_ts(request: Request, p: Path, key: str = "ts"):
    q = dict(parse_qsl(request.url.query))
    if key in q:
        return None

    q[key] = str(file_mtime_ts(p))
    parsed = urlparse(str(request.url))
    new_url = urlunparse(parsed._replace(query=urlencode(q)))
    return RedirectResponse(new_url, status_code=302)