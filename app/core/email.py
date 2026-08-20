from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import Settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_templates = Environment(
    loader=FileSystemLoader(os.path.join(_PROJECT_ROOT, "views")),
    autoescape=select_autoescape(["html"]),
)


def _cfg() -> Settings:
    """Read .env at send time so mail settings apply without a process restart."""
    return Settings()


def _sanitize(message: str, password: str = "") -> str:
    secret = (password or "").strip()
    if secret and secret in message:
        message = message.replace(secret, "********")
    return message


def _site_url() -> str:
    return (_cfg().SITE_URL or "").rstrip("/")


def render_email(template: str, context: dict[str, Any]) -> str:
    return _templates.get_template(template).render(**context)


def send_email(to_address: str, subject: str, html_body: str) -> bool:
    """Send one HTML email. Never raises. Never logs MAIL_PASSWORD."""
    cfg = _cfg()
    to_address = (to_address or "").strip()
    host = (cfg.MAIL_HOST or "").strip()
    from_address = (cfg.MAIL_FROM_ADDRESS or "").strip()
    password = cfg.MAIL_PASSWORD or ""
    if not to_address or "@" not in to_address:
        logger.warning("Skipping email; missing or invalid recipient")
        return False
    if not host or not from_address:
        logger.warning("Skipping email; MAIL_HOST or MAIL_FROM_ADDRESS is not set")
        return False

    from_name = (cfg.MAIL_FROM_NAME or "N Designs").strip()
    username = (cfg.MAIL_USERNAME or from_address).strip()
    port = int(cfg.MAIL_PORT or 465)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_address))
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            if username:
                smtp.login(username, password)
            smtp.sendmail(from_address, [parseaddr(to_address)[1] or to_address], msg.as_string())
        logger.warning("Sent email '%s' to %s", subject, to_address)
        return True
    except Exception as exc:
        logger.error(
            "Failed to send email '%s' to %s via %s:%s (%s: %s)",
            subject,
            to_address,
            host,
            port,
            type(exc).__name__,
            _sanitize(str(exc), password),
        )
        return False


def send_order_emails(payload: dict[str, Any]) -> None:
    """Customer confirmation + admin alert. Failures are logged; never raised."""
    cfg = _cfg()
    site = (cfg.SITE_URL or "").rstrip("/")
    number = payload["order_number"]
    context = {
        **payload,
        "site_url": site,
        "contact_phone": cfg.contact_display,
        "whatsapp_url": cfg.whatsapp_url,
        "contact_tel": cfg.contact_tel,
    }

    customer_to = payload.get("customer_email") or ""
    customer_html = render_email("emails/order_confirmation.html", context)
    send_email(
        customer_to,
        f"Order {number} confirmed — N Designs",
        customer_html,
    )

    admin_to = (cfg.ADMIN_NOTIFICATION_EMAIL or "").strip()
    if not admin_to:
        logger.warning("Skipping admin order email; ADMIN_NOTIFICATION_EMAIL is not set")
    else:
        admin_html = render_email("emails/new_order_admin.html", context)
        send_email(
            admin_to,
            f"New order {number} — {payload['total_label']}",
            admin_html,
        )
