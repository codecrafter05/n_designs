from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Customer, CustomerSession

COOKIE_NAME = "customer_session"
COOKIE_MAX_AGE = 60 * 24 * 60 * 60
SESSION_DAYS = 60


def new_session_token() -> str:
    return uuid4().hex


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_current_customer(request: Request, db: Session) -> Customer | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    row = (
        db.query(CustomerSession)
        .options(selectinload(CustomerSession.customer))
        .filter(CustomerSession.session_token == token)
        .first()
    )
    if row is None:
        return None
    if _aware(row.expires_at) < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        return None
    return row.customer


def create_customer_session(response: Response, db: Session, customer: Customer) -> None:
    token = new_session_token()
    now = datetime.now(timezone.utc)
    db.add(
        CustomerSession(
            customer_id=customer.id,
            session_token=token,
            created_at=now,
            expires_at=now + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def destroy_customer_session(request: Request, response: Response, db: Session) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = (
            db.query(CustomerSession)
            .filter(CustomerSession.session_token == token)
            .first()
        )
        if row is not None:
            db.delete(row)
            db.commit()
    response.delete_cookie(key=COOKIE_NAME, path="/")
