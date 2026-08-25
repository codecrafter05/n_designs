"""Honeypot + per-IP rate limits for public storefront POST forms.

No extra services: a CSS-hidden text field named ``website_url``, and a
file-backed sliding window shared across uvicorn workers. Bots that fill the
honeypot are redirected home with 303 as if the submit succeeded.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

HONEYPOT_FIELD = "website_url"
RATE_LIMIT_MESSAGE = "Please try again later."
_SILENT_REDIRECT = "/"
_STATE_PATH = os.environ.get("FORM_LIMIT_PATH", "/tmp/ndesigns-form-limits.json")

# path -> (max submissions, window seconds)
_LIMITS: dict[str, tuple[int, int]] = {
    "/register": (5, 15 * 60),
    "/checkout": (8, 10 * 60),
}

_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # nginx sets X-Real-IP to $remote_addr (not client-spoofable). Prefer it
    # over X-Forwarded-For, whose left-most value a bot can prefix.
    real = (request.headers.get("x-real-ip") or "").strip()
    if real:
        return real
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def silent_reject(request: Request | None = None) -> RedirectResponse:
    if request is not None:
        logger.info("honeypot filled on %s from %s", request.url.path, client_ip(request))
    return RedirectResponse(url=_SILENT_REDIRECT, status_code=303)


def honeypot_filled(value: str | None) -> bool:
    return bool((value or "").strip())


def _load_hits(handle) -> dict[str, list[float]]:
    handle.seek(0)
    raw = handle.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, list[float]] = {}
    for key, stamps in data.items():
        if isinstance(key, str) and isinstance(stamps, list):
            cleaned[key] = [float(s) for s in stamps if isinstance(s, (int, float))]
    return cleaned


def is_rate_limited(request: Request, path: str | None = None) -> bool:
    route = path or request.url.path
    limit = _LIMITS.get(route)
    if limit is None:
        return False
    max_hits, window = limit
    key = f"{client_ip(request)}|{route}"
    now = time.time()
    cutoff = now - window
    with _lock:
        os.makedirs(os.path.dirname(_STATE_PATH) or ".", exist_ok=True)
        with open(_STATE_PATH, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            hits = _load_hits(handle)
            bucket = [stamp for stamp in hits.get(key, []) if stamp >= cutoff]
            if len(bucket) >= max_hits:
                hits[key] = bucket
                _write_hits(handle, hits, now)
                logger.info("rate limited %s from %s", route, key.split("|", 1)[0])
                return True
            bucket.append(now)
            hits[key] = bucket
            _write_hits(handle, hits, now)
            return False


def _write_hits(handle, hits: dict[str, list[float]], now: float) -> None:
    pruned: dict[str, list[float]] = {}
    for key, stamps in hits.items():
        route = key.rsplit("|", 1)[-1]
        window = _LIMITS[route][1] if route in _LIMITS else 15 * 60
        kept = [stamp for stamp in stamps if stamp >= now - window]
        if kept:
            pruned[key] = kept
    handle.seek(0)
    handle.truncate()
    json.dump(pruned, handle)
    handle.flush()
