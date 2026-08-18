from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.v1.endpoints.web import COUNTRIES, _fmt_bhd, _storefront_page
from app.core.customer_auth import (
    create_customer_session,
    destroy_customer_session,
    get_current_customer,
)
from app.core.database import get_db
from app.core.orders import order_number
from app.core.security import hash_password, verify_password
from app.models.customer import Customer
from app.models.order import Order

router = APIRouter(tags=["account"])

MIN_PASSWORD_LEN = 8


def _safe_next(raw: str | None) -> str:
    path = (raw or "").strip()
    if path.startswith("/") and not path.startswith("//") and "://" not in path:
        return path
    return "/account"


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=303)


def _find_by_email(db: Session, email: str) -> Customer | None:
    return db.query(Customer).filter(func.lower(Customer.email) == email).first()


def _auth_page(request: Request, db: Session, template: str, **extra):
    return _storefront_page(request, template, db=db, **extra)


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_get(request: Request, db: Session = Depends(get_db), next: str | None = None):
    if get_current_customer(request, db):
        return _redirect(_safe_next(next))
    return _auth_page(
        request,
        db,
        "storefront/register.html",
        form={"name": "", "email": "", "phone": ""},
        next_path=_safe_next(next) if next else "",
        auth_error=None,
    )


@router.post("/register", include_in_schema=False)
def register_post(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    next: str = Form(""),
):
    form = {"name": name.strip(), "email": email.strip(), "phone": phone.strip()}
    next_path = _safe_next(next) if next else "/account"
    if get_current_customer(request, db):
        return _redirect(next_path)

    def fail(message: str):
        return _auth_page(
            request,
            db,
            "storefront/register.html",
            form=form,
            next_path=next if next else "",
            auth_error=message,
        )

    if not form["name"]:
        return fail("Please enter your name.")
    if not form["email"] or "@" not in form["email"]:
        return fail("Please enter a valid email.")
    if len(password) < MIN_PASSWORD_LEN:
        return fail(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    if password != confirm_password:
        return fail("Passwords do not match.")

    email_key = form["email"].lower()
    existing = _find_by_email(db, email_key)
    if existing is not None and existing.hashed_password:
        return fail("An account with this email already exists — log in instead")

    hashed = hash_password(password)
    if existing is not None:
        existing.email = email_key
        existing.name = form["name"]
        existing.hashed_password = hashed
        if form["phone"]:
            existing.phone = form["phone"]
        customer = existing
    else:
        customer = Customer(
            name=form["name"],
            email=email_key,
            hashed_password=hashed,
            phone=form["phone"],
        )
        db.add(customer)
    db.commit()
    db.refresh(customer)

    response = _redirect(next_path)
    create_customer_session(response, db, customer)
    return response


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_get(request: Request, db: Session = Depends(get_db), next: str | None = None):
    if get_current_customer(request, db):
        return _redirect(_safe_next(next))
    return _auth_page(
        request,
        db,
        "storefront/login.html",
        form={"email": ""},
        next_path=_safe_next(next) if next else "",
        auth_error=None,
    )


@router.post("/login", include_in_schema=False)
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
):
    form = {"email": email.strip()}
    next_path = _safe_next(next) if next else "/account"
    if get_current_customer(request, db):
        return _redirect(next_path)

    email_key = form["email"].lower()
    customer = _find_by_email(db, email_key) if email_key else None
    valid = bool(
        customer
        and customer.hashed_password
        and verify_password(password, customer.hashed_password)
    )
    if not valid:
        return _auth_page(
            request,
            db,
            "storefront/login.html",
            form=form,
            next_path=next if next else "",
            auth_error="Invalid email or password",
        )

    response = _redirect(next_path)
    create_customer_session(response, db, customer)
    return response


@router.post("/logout", include_in_schema=False)
def logout_post(request: Request, db: Session = Depends(get_db)):
    response = _redirect("/")
    destroy_customer_session(request, response, db)
    return response


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _profile_form(customer: Customer, data: dict | None = None) -> dict:
    first, last = _split_name(customer.name)
    data = data or {}
    return {
        "first_name": (data.get("first_name") if data.get("first_name") is not None else first).strip(),
        "last_name": (data.get("last_name") if data.get("last_name") is not None else last).strip(),
        "email": (data.get("email") if data.get("email") is not None else (customer.email or "")).strip(),
        "phone": (data.get("phone") if data.get("phone") is not None else (customer.phone or "")).strip(),
        "address": (data.get("address") if data.get("address") is not None else (customer.address or "")).strip(),
        "city": (data.get("city") if data.get("city") is not None else (customer.city or "")).strip(),
        "country": (data.get("country") if data.get("country") is not None else (customer.country or "Bahrain")).strip(),
    }


_ORDER_BADGE = {
    "pending": "sf-badge-neutral",
    "processing": "sf-badge-progress",
    "shipped": "sf-badge-progress",
    "delivered": "sf-badge-done",
    "cancelled": "sf-badge-cancel",
}
_ORDER_LABEL = {
    "pending": "Pending",
    "processing": "Processing",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def _require_customer(request: Request, db: Session, next_path: str):
    customer = get_current_customer(request, db)
    if customer is None:
        return None, _redirect("/login?" + urlencode({"next": next_path}))
    return customer, None


@router.get("/account", response_class=HTMLResponse, include_in_schema=False)
def account_page(request: Request, db: Session = Depends(get_db)):
    customer, denied = _require_customer(request, db, "/account")
    if denied:
        return denied
    orders = (
        db.query(Order)
        .filter(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    order_rows = [
        {
            "id": order.id,
            "number": order_number(order.id),
            "date": order.created_at.strftime("%d %b %Y") if order.created_at else "—",
            "status_label": _ORDER_LABEL.get(order.status, order.status.title()),
            "badge_class": _ORDER_BADGE.get(order.status, "sf-badge-neutral"),
            "total_label": _fmt_bhd(order.total),
        }
        for order in orders
    ]
    return _storefront_page(
        request,
        "storefront/account.html",
        db=db,
        customer=customer,
        orders=order_rows,
        notice=request.query_params.get("notice"),
    )


@router.get("/account/edit", response_class=HTMLResponse, include_in_schema=False)
def account_edit_get(request: Request, db: Session = Depends(get_db)):
    customer, denied = _require_customer(request, db, "/account/edit")
    if denied:
        return denied
    return _storefront_page(
        request,
        "storefront/account-edit.html",
        db=db,
        form=_profile_form(customer),
        countries=COUNTRIES,
        auth_error=None,
    )


@router.post("/account/edit", include_in_schema=False)
def account_edit_post(
    request: Request,
    db: Session = Depends(get_db),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
):
    customer, denied = _require_customer(request, db, "/account/edit")
    if denied:
        return denied

    form = _profile_form(
        customer,
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "city": city,
            "country": country,
        },
    )

    def fail(message: str):
        return _storefront_page(
            request,
            "storefront/account-edit.html",
            db=db,
            form=form,
            countries=COUNTRIES,
            auth_error=message,
        )

    missing = [
        label
        for key, label in (
            ("email", "Email"),
            ("first_name", "First name"),
            ("last_name", "Last name"),
            ("address", "Address"),
            ("city", "City"),
            ("country", "Country"),
            ("phone", "Phone"),
        )
        if not form[key]
    ]
    if missing:
        return fail("Please fill in: " + ", ".join(missing) + ".")
    if "@" not in form["email"]:
        return fail("Please enter a valid email.")

    email_key = form["email"].lower()
    other = _find_by_email(db, email_key)
    if other is not None and other.id != customer.id:
        return fail("This email is already in use")

    customer.name = f"{form['first_name']} {form['last_name']}".strip()
    customer.email = email_key
    customer.phone = form["phone"]
    customer.address = form["address"]
    customer.city = form["city"]
    customer.country = form["country"]
    db.commit()
    return _redirect("/account?" + urlencode({"notice": "Profile updated"}))
