import os
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.discounts import normalize_code
from app.models.discount import DiscountCode

router = APIRouter(tags=["admin-discount-codes"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _pct_label(value) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.01"))
    if number == number.to_integral():
        return f"{int(number)}%"
    return f"{number.normalize()}%"


def _usage_label(row: DiscountCode) -> str:
    used = row.times_used or 0
    if row.max_uses is None:
        return f"{used} / ∞"
    return f"{used} / {row.max_uses}"


def _list_row(row: DiscountCode) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "percentage_label": _pct_label(row.percentage),
        "usage_label": _usage_label(row),
        "applies_to_sale": row.applies_to_sale_items,
        "is_active": row.is_active,
        "created_label": row.created_at.strftime("%d %b %Y") if row.created_at else "—",
    }


def _code_taken(db: Session, code: str, exclude_id: int | None = None) -> bool:
    query = db.query(DiscountCode).filter(func.upper(DiscountCode.code) == code)
    if exclude_id is not None:
        query = query.filter(DiscountCode.id != exclude_id)
    return query.first() is not None


def _parse_percentage(raw: str) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if value < 1 or value > 100:
        return None
    return value.quantize(Decimal("0.01"))


def _parse_max_uses(raw: str) -> int | None | str:
    text = (raw or "").strip()
    if not text:
        return None
    if not text.isdigit() or int(text) < 1:
        return "invalid"
    return int(text)


@router.get("/admin/discount-codes", response_class=HTMLResponse, include_in_schema=False)
def discount_codes_list(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(DiscountCode)
        .order_by(DiscountCode.created_at.desc(), DiscountCode.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/discount_codes/index.html",
        {
            "request": request,
            "rows": [_list_row(row) for row in rows],
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get(
    "/admin/discount-codes/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def discount_codes_new(request: Request):
    return templates.TemplateResponse(
        "admin/discount_codes/form.html",
        {
            "request": request,
            "row": None,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/discount-codes/new", include_in_schema=False)
def discount_codes_create(
    code: str = Form(""),
    percentage: str = Form(""),
    max_uses: str = Form(""),
    applies_to_sale_items: str = Form(""),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
):
    key = normalize_code(code)
    if not key:
        return _redirect("/admin/discount-codes/new", error="Code is required.")
    pct = _parse_percentage(percentage)
    if pct is None:
        return _redirect(
            "/admin/discount-codes/new",
            error="Percentage must be between 1 and 100.",
        )
    uses = _parse_max_uses(max_uses)
    if uses == "invalid":
        return _redirect(
            "/admin/discount-codes/new",
            error="Max uses must be 1 or more, or leave empty for unlimited.",
        )
    if _code_taken(db, key):
        return _redirect(
            "/admin/discount-codes/new",
            error="A discount code with this name already exists.",
        )
    row = DiscountCode(
        code=key,
        percentage=pct,
        max_uses=uses,
        times_used=0,
        applies_to_sale_items=applies_to_sale_items == "1",
        is_active=is_active == "1",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _redirect(
            "/admin/discount-codes/new",
            error="A discount code with this name already exists.",
        )
    return _redirect("/admin/discount-codes", notice="Discount code created.")


@router.get(
    "/admin/discount-codes/{code_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def discount_codes_edit(code_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.query(DiscountCode).filter(DiscountCode.id == code_id).first()
    if row is None:
        return _redirect("/admin/discount-codes", error="Discount code not found.")
    return templates.TemplateResponse(
        "admin/discount_codes/form.html",
        {
            "request": request,
            "row": row,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/discount-codes/{code_id}/edit", include_in_schema=False)
def discount_codes_update(
    code_id: int,
    code: str = Form(""),
    percentage: str = Form(""),
    max_uses: str = Form(""),
    applies_to_sale_items: str = Form(""),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
):
    row = db.query(DiscountCode).filter(DiscountCode.id == code_id).first()
    if row is None:
        return _redirect("/admin/discount-codes", error="Discount code not found.")
    key = normalize_code(code)
    if not key:
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit", error="Code is required."
        )
    pct = _parse_percentage(percentage)
    if pct is None:
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit",
            error="Percentage must be between 1 and 100.",
        )
    uses = _parse_max_uses(max_uses)
    if uses == "invalid":
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit",
            error="Max uses must be 1 or more, or leave empty for unlimited.",
        )
    if uses is not None and uses < row.times_used:
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit",
            error="Max uses cannot be lower than times already used.",
        )
    if _code_taken(db, key, exclude_id=row.id):
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit",
            error="A discount code with this name already exists.",
        )
    row.code = key
    row.percentage = pct
    row.max_uses = uses
    row.applies_to_sale_items = applies_to_sale_items == "1"
    row.is_active = is_active == "1"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _redirect(
            f"/admin/discount-codes/{code_id}/edit",
            error="A discount code with this name already exists.",
        )
    return _redirect("/admin/discount-codes", notice="Discount code updated.")
