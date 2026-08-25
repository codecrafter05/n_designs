"""Signed arithmetic CAPTCHA for /register. No extra packages or tables.

The hidden field carries expiry + nonce and an HMAC-SHA256 of
(purpose, expiry, nonce, answer) using SECRET_KEY. The numeric answer is
never written into the HTML. A bot that copies the hidden value cannot
read the answer from it, and cannot swap in a different answer without
the key.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
import time

from app.core.config import settings

CAPTCHA_WRONG = "That answer wasn't quite right — try again"
_TTL_SECONDS = 30 * 60
_PURPOSE = "math-captcha"


def new_challenge() -> dict[str, str]:
    left = random.randint(1, 10)
    right = random.randint(1, 10)
    if random.choice(("+", "-")) == "+":
        op = "+"
        answer = left + right
    else:
        op = "-"
        if left < right:
            left, right = right, left
        answer = left - right
    return {
        "question": f"What is {left} {op} {right}?",
        "token": _sign(answer),
    }


def answer_is_correct(token: str | None, submitted: str | None) -> bool:
    parsed = _parse_int(submitted)
    if parsed is None:
        return False
    public = _parse_public(token)
    if public is None:
        return False
    payload, given = public
    expected = _digest(f"{payload}:{parsed}")
    return hmac.compare_digest(expected, given)


def _parse_int(raw: str | None) -> int | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _sign(answer: int) -> str:
    exp = int(time.time()) + _TTL_SECONDS
    nonce = secrets.token_hex(8)
    payload = f"{_PURPOSE}:{exp}:{nonce}"
    return f"{payload}.{_digest(f'{payload}:{answer}')}"


def _digest(payload: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def _parse_public(token: str | None) -> tuple[str, str] | None:
    raw = (token or "").strip()
    if "." not in raw:
        return None
    payload, given = raw.rsplit(".", 1)
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != _PURPOSE:
        return None
    try:
        exp = int(parts[1])
    except ValueError:
        return None
    if exp < int(time.time()):
        return None
    if not given:
        return None
    return payload, given
