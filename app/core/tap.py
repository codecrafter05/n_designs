from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal

from app.core.config import Settings

logger = logging.getLogger(__name__)

TAP_API = "https://api.tap.company"
TAP_START_ERROR = "Couldn't start payment, please try again"


class TapError(Exception):
    pass


def _cfg() -> Settings:
    return Settings()


def _secret() -> str:
    return (_cfg().TAP_SECRET_KEY or "").strip()


def tap_configured() -> bool:
    return bool(_secret())


def split_phone(raw: str) -> dict:
    text = (raw or "").strip().replace(" ", "").replace("-", "")
    if text.startswith("+"):
        text = text[1:]
    for code in ("973", "966", "971", "965"):
        if text.startswith(code) and len(text) > len(code):
            return {"country_code": code, "number": text[len(code) :]}
    return {"country_code": "973", "number": text or "00000000"}


def _request(method: str, path: str, body: dict | None = None) -> dict:
    key = _secret()
    if not key:
        raise TapError("Tap is not configured")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{TAP_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        logger.warning("Tap API HTTP %s %s body=%s", exc.code, path, raw[:800])
        raise TapError(f"Tap HTTP {exc.code}") from exc
    except Exception as exc:
        logger.warning("Tap API %s %s failed: %s", method, path, type(exc).__name__)
        raise TapError("Tap request failed") from exc
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        logger.warning("Tap API %s returned non-JSON", path)
        raise TapError("Tap returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise TapError("Tap returned an unexpected payload")
    return payload


def create_charge(
    *,
    amount: Decimal,
    currency: str,
    token: str,
    form: dict,
    redirect_url: str,
    description: str,
) -> dict:
    amount_value = float(Decimal(str(amount)).quantize(Decimal("0.001")))
    payload = {
        "amount": amount_value,
        "currency": currency,
        "threeDSecure": True,
        "save_card": False,
        "description": description,
        "statement_descriptor": "N Designs",
        "reference": {"transaction": token, "order": token},
        "receipt": {"email": False, "sms": False},
        "customer": {
            "first_name": form["first_name"],
            "last_name": form["last_name"],
            "email": form["email"],
            "phone": split_phone(form["phone"]),
        },
        "source": {"id": "src_all"},
        "redirect": {"url": redirect_url},
    }
    charge = _request("POST", "/v2/charges", payload)
    charge_id = charge.get("id")
    logger.warning(
        "Tap create charge session=%s charge=%s status=%s",
        token,
        charge_id,
        charge.get("status"),
    )
    return charge


def retrieve_charge(charge_id: str) -> dict:
    path = f"/v2/charges/{charge_id}"
    charge = _request("GET", path)
    logger.warning(
        "Tap retrieve charge=%s status=%s amount=%s currency=%s",
        charge.get("id"),
        charge.get("status"),
        charge.get("amount"),
        charge.get("currency"),
    )
    return charge
