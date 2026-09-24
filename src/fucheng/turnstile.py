"""Server-side Turnstile verification, outside SQLite write transactions."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from fastapi import HTTPException

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
ACTION = "public_registration"


def verify_turnstile(token: str | None, settings, remote_ip: str) -> None:
    if settings.turnstile_mode == "disabled":
        return
    if not token or len(token) > 2048:
        raise HTTPException(422, "請完成安全驗證後再送出")
    body = urlencode({"secret": settings.turnstile_secret, "response": token,
                      "remoteip": remote_ip}).encode("ascii")
    request = Request(SITEVERIFY, data=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=3) as response:
            if response.status != 200:
                raise HTTPException(503, "安全驗證暫時無法連線，請稍後再試")
            raw = response.read(8193)
        if len(raw) > 8192:
            raise ValueError("Siteverify response too large")
        result = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        # Neither token nor secret enters the response or application logs.
        raise HTTPException(503, "安全驗證暫時無法連線，請稍後再試") from None
    if not isinstance(result, dict):
        raise HTTPException(503, "安全驗證暫時無法連線，請稍後再試")
    if result.get("success") is not True:
        raise HTTPException(422, "安全驗證未通過，請再試一次")
    hostname = settings.turnstile_hostname or urlsplit(settings.public_origin or "").hostname
    if result.get("hostname") != hostname or result.get("action") != ACTION:
        raise HTTPException(422, "安全驗證未通過，請再試一次")
    try:
        challenge_time = datetime.fromisoformat(result["challenge_ts"].replace("Z", "+00:00"))
        if challenge_time.tzinfo is None:
            raise ValueError("Missing Siteverify timezone")
        age = datetime.now(UTC) - challenge_time.astimezone(UTC)
    except (KeyError, AttributeError, TypeError, ValueError):
        raise HTTPException(422, "安全驗證未通過，請再試一次") from None
    if not -timedelta(seconds=30) <= age <= timedelta(seconds=300):
        raise HTTPException(422, "安全驗證已逾時，請再試一次")
