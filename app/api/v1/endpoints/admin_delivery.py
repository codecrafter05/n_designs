import json
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.delivery import DeliveryGroup, DeliveryGroupCountry, DeliveryWeightTier

router = APIRouter(tags=["admin-delivery"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))
MONEY = Decimal("0.001")
WEIGHT = Decimal("0.001")


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _money_label(value) -> str:
    number = Decimal(str(value or 0)).quantize(MONEY)
    return f"{number:.3f}"


def _load_group(db: Session, group_id: int) -> DeliveryGroup | None:
    return (
        db.query(DeliveryGroup)
        .options(
            selectinload(DeliveryGroup.countries),
            selectinload(DeliveryGroup.tiers),
        )
        .filter(DeliveryGroup.id == group_id)
        .first()
    )


def _list_row(row: DeliveryGroup) -> dict:
    countries = sorted(c.country_name for c in row.countries)
    return {
        "id": row.id,
        "name": row.name,
        "countries_label": ", ".join(countries) if countries else "—",
        "handling_label": _money_label(row.handling_fee),
        "tier_count": len(row.tiers),
    }


def _form_payload(row: DeliveryGroup | None) -> dict:
    if row is None:
        return {
            "name": "",
            "handling_fee": "0.000",
            "countries_json": "[]",
            "tiers_json": "[]",
        }
    countries = [c.country_name for c in row.countries]
    tiers = sorted(
        row.tiers,
        key=lambda t: (Decimal(str(t.max_weight_kg)), t.id),
    )
    return {
        "name": row.name,
        "handling_fee": _money_label(row.handling_fee),
        "countries_json": json.dumps(countries),
        "tiers_json": json.dumps(
            [
                {
                    "max_weight_kg": str(Decimal(str(t.max_weight_kg))),
                    "price": _money_label(t.price),
                }
                for t in tiers
            ]
        ),
    }


def _parse_decimal(raw, *, label: str, allow_zero: bool = True) -> Decimal:
    text = str(raw or "").strip()
    if not text:
        raise ValueError(f"{label} is required.")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    if not allow_zero and value == 0:
        raise ValueError(f"{label} must be greater than zero.")
    return value


def _parse_handling(raw: str) -> Decimal:
    text = (raw or "").strip()
    if not text:
        return Decimal("0.000")
    return _parse_decimal(text, label="Handling fee").quantize(MONEY)


def _parse_countries(raw: str) -> list[str]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Country list is invalid.") from exc
    if not isinstance(payload, list):
        raise ValueError("Country list is invalid.")
    names: list[str] = []
    seen: set[str] = set()
    for item in payload:
        name = str(item or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            raise ValueError(f"“{name}” is listed more than once.")
        seen.add(key)
        names.append(name)
    if not names:
        raise ValueError("Add at least one country.")
    return names


def _parse_tiers(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Weight tiers are invalid.") from exc
    if not isinstance(payload, list):
        raise ValueError("Weight tiers are invalid.")
    tiers = []
    seen: set[Decimal] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Weight tiers are invalid.")
        max_kg = _parse_decimal(
            item.get("max_weight_kg"), label="Weight", allow_zero=False
        ).quantize(WEIGHT)
        price = _parse_decimal(item.get("price"), label="Price").quantize(MONEY)
        if max_kg in seen:
            raise ValueError("Each tier needs a different max weight.")
        seen.add(max_kg)
        tiers.append({"max_weight_kg": max_kg, "price": price})
    tiers.sort(key=lambda row: row["max_weight_kg"])
    return tiers


def _country_taken(
    db: Session, names: list[str], exclude_group_id: int | None = None
) -> str | None:
    keys = [name.lower() for name in names]
    query = db.query(DeliveryGroupCountry).filter(
        func.lower(DeliveryGroupCountry.country_name).in_(keys)
    )
    if exclude_group_id is not None:
        query = query.filter(DeliveryGroupCountry.group_id != exclude_group_id)
    clash = query.first()
    if clash is None:
        return None
    return clash.country_name


def _next_display_order(db: Session) -> int:
    current = db.query(func.max(DeliveryGroup.display_order)).scalar()
    return int(current or 0) + 1


def _replace_children(
    db: Session,
    group: DeliveryGroup,
    countries: list[str],
    tiers: list[dict],
) -> None:
    db.query(DeliveryGroupCountry).filter(
        DeliveryGroupCountry.group_id == group.id
    ).delete()
    db.query(DeliveryWeightTier).filter(
        DeliveryWeightTier.group_id == group.id
    ).delete()
    for name in countries:
        db.add(DeliveryGroupCountry(group_id=group.id, country_name=name))
    for tier in tiers:
        db.add(
            DeliveryWeightTier(
                group_id=group.id,
                max_weight_kg=tier["max_weight_kg"],
                price=tier["price"],
            )
        )


def _form_page(
    request: Request,
    *,
    row: DeliveryGroup | None,
    error: str | None = None,
    form: dict | None = None,
):
    payload = form or _form_payload(row)
    return templates.TemplateResponse(
        "admin/delivery/form.html",
        {
            "request": request,
            "row": row,
            "error": error or request.query_params.get("error"),
            **payload,
        },
    )


@router.get("/admin/delivery-prices", response_class=HTMLResponse, include_in_schema=False)
def delivery_list(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(DeliveryGroup)
        .options(
            selectinload(DeliveryGroup.countries),
            selectinload(DeliveryGroup.tiers),
        )
        .order_by(DeliveryGroup.display_order, DeliveryGroup.id)
        .all()
    )
    return templates.TemplateResponse(
        "admin/delivery/index.html",
        {
            "request": request,
            "rows": [_list_row(row) for row in rows],
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get(
    "/admin/delivery-prices/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def delivery_new(request: Request):
    return _form_page(request, row=None)


@router.post("/admin/delivery-prices/new", include_in_schema=False)
def delivery_create(
    request: Request,
    name: str = Form(""),
    handling_fee: str = Form(""),
    countries_json: str = Form("[]"),
    tiers_json: str = Form("[]"),
    db: Session = Depends(get_db),
):
    label = (name or "").strip()
    form = {
        "name": label,
        "handling_fee": handling_fee,
        "countries_json": countries_json,
        "tiers_json": tiers_json,
    }
    if not label:
        return _form_page(request, row=None, error="Label is required.", form=form)
    try:
        fee = _parse_handling(handling_fee)
        countries = _parse_countries(countries_json)
        tiers = _parse_tiers(tiers_json)
    except ValueError as exc:
        return _form_page(request, row=None, error=str(exc), form=form)
    clash = _country_taken(db, countries)
    if clash:
        return _form_page(
            request,
            row=None,
            error=f"“{clash}” is already used on another delivery group.",
            form=form,
        )
    group = DeliveryGroup(
        name=label,
        handling_fee=fee,
        display_order=_next_display_order(db),
    )
    db.add(group)
    db.flush()
    _replace_children(db, group, countries, tiers)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _form_page(
            request,
            row=None,
            error="A country on this group is already used elsewhere.",
            form=form,
        )
    return _redirect("/admin/delivery-prices", notice="Delivery prices saved.")


@router.get(
    "/admin/delivery-prices/{group_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def delivery_edit(group_id: int, request: Request, db: Session = Depends(get_db)):
    row = _load_group(db, group_id)
    if row is None:
        return _redirect("/admin/delivery-prices", error="Delivery group not found.")
    return _form_page(request, row=row)


@router.post("/admin/delivery-prices/{group_id}/edit", include_in_schema=False)
def delivery_update(
    group_id: int,
    request: Request,
    name: str = Form(""),
    handling_fee: str = Form(""),
    countries_json: str = Form("[]"),
    tiers_json: str = Form("[]"),
    db: Session = Depends(get_db),
):
    row = _load_group(db, group_id)
    if row is None:
        return _redirect("/admin/delivery-prices", error="Delivery group not found.")
    label = (name or "").strip()
    form = {
        "name": label,
        "handling_fee": handling_fee,
        "countries_json": countries_json,
        "tiers_json": tiers_json,
    }
    if not label:
        return _form_page(request, row=row, error="Label is required.", form=form)
    try:
        fee = _parse_handling(handling_fee)
        countries = _parse_countries(countries_json)
        tiers = _parse_tiers(tiers_json)
    except ValueError as exc:
        return _form_page(request, row=row, error=str(exc), form=form)
    clash = _country_taken(db, countries, exclude_group_id=row.id)
    if clash:
        return _form_page(
            request,
            row=row,
            error=f"“{clash}” is already used on another delivery group.",
            form=form,
        )
    row.name = label
    row.handling_fee = fee
    _replace_children(db, row, countries, tiers)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _form_page(
            request,
            row=row,
            error="A country on this group is already used elsewhere.",
            form=form,
        )
    return _redirect("/admin/delivery-prices", notice="Delivery prices updated.")
