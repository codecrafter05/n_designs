from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.api.v1.endpoints.web import _fmt_bhd, _payable
from app.core.cart import get_or_create_cart, reload_cart, set_cart_cookie
from app.core.customer_auth import get_current_customer
from app.core.database import get_db
from app.core.discounts import GENERIC_INVALID, cart_pricing, find_code, is_usable
from app.core.measurements import normalize_inches, save_customer_measurement, size_label
from app.models.cart import Cart, CartItem
from app.models.product import Product, ProductColor, ProductVariant

router = APIRouter(tags=["cart"])


class AddIn(BaseModel):
    product_variant_id: int
    quantity: int = 1
    is_custom: bool = False
    custom_length: str = ""
    custom_chest: str = ""
    line_comment: str = ""
    save_measurement: bool = False


class UpdateIn(BaseModel):
    cart_item_id: int
    quantity: int = Field(..., ge=0)


class RemoveIn(BaseModel):
    cart_item_id: int


class ApplyCodeIn(BaseModel):
    code: str = ""


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _payload(cart: Cart, extra: dict | None = None) -> dict:
    count = sum(item.quantity for item in cart.items)
    pricing = cart_pricing(cart)
    data = {
        "ok": True,
        "count": count,
        "subtotal_label": _fmt_bhd(pricing.subtotal) if count else _fmt_bhd(0),
        "discount_code": pricing.discount_code,
        "discount_amount_label": _fmt_bhd(pricing.discount_amount),
        "total_label": _fmt_bhd(pricing.payable_total) if count else _fmt_bhd(0),
    }
    if extra:
        data.update(extra)
    return data


def _json(cart: Cart, token: str, needs_cookie: bool, extra: dict | None = None) -> JSONResponse:
    response = JSONResponse(_payload(cart, extra))
    if needs_cookie:
        set_cart_cookie(response, token)
    return response


def _load_variant(db: Session, variant_id: int) -> ProductVariant | None:
    return (
        db.query(ProductVariant)
        .options(
            selectinload(ProductVariant.color)
            .selectinload(ProductColor.product)
            .selectinload(Product.images)
        )
        .filter(ProductVariant.id == variant_id)
        .first()
    )


def _norm_comment(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _item_matches(
    item: CartItem,
    *,
    variant_id: int,
    is_custom: bool,
    custom_length: str | None,
    custom_chest: str | None,
    line_comment: str | None,
) -> bool:
    return (
        item.product_variant_id == variant_id
        and bool(item.is_custom) == bool(is_custom)
        and (item.custom_length or None) == (custom_length or None)
        and (item.custom_chest or None) == (custom_chest or None)
        and (item.line_comment or None) == (line_comment or None)
    )


def _item_info(item: CartItem) -> dict:
    variant = item.variant
    color = variant.color if variant else None
    product = color.product if color else None
    thumb = None
    if product and product.images:
        thumb = product.images[0].image_url
    label = size_label(
        is_custom=bool(item.is_custom),
        custom_length=item.custom_length,
        custom_chest=item.custom_chest,
        variant_size=variant.size if variant else "",
    )
    return {
        "id": item.id,
        "product_variant_id": item.product_variant_id,
        "quantity": item.quantity,
        "name": product.name if product else "",
        "image": thumb,
        "color": color.color_name if color else "",
        "size": label,
        "is_custom": bool(item.is_custom),
        "custom_length": item.custom_length or "",
        "custom_chest": item.custom_chest or "",
        "line_comment": item.line_comment or "",
        "save_measurement": bool(item.save_measurement),
    }


def _touch(cart: Cart) -> None:
    cart.updated_at = datetime.now(timezone.utc)


@router.post("/cart/add", include_in_schema=False)
def cart_add(body: AddIn, request: Request, db: Session = Depends(get_db)):
    qty = body.quantity if body.quantity > 0 else 1
    variant = _load_variant(db, body.product_variant_id)
    if variant is None or variant.color is None or variant.color.product is None:
        return _error("This piece is no longer available.")
    if not variant.color.product.is_active:
        return _error("This piece is no longer available.")
    if variant.stock_quantity <= 0:
        return _error("This size is out of stock.")

    is_custom = bool(body.is_custom)
    custom_length = normalize_inches(body.custom_length) if is_custom else None
    custom_chest = normalize_inches(body.custom_chest) if is_custom else None
    line_comment = _norm_comment(body.line_comment)
    save_measurement = bool(body.save_measurement) if is_custom else False

    if is_custom:
        if not custom_length or not custom_chest:
            return _error("Please enter Item Length and Chest for a custom size.")
        custom_length = custom_length[:50]
        custom_chest = custom_chest[:50]

    cart, token, needs_cookie = get_or_create_cart(db, request)
    existing = next(
        (
            item
            for item in cart.items
            if _item_matches(
                item,
                variant_id=variant.id,
                is_custom=is_custom,
                custom_length=custom_length,
                custom_chest=custom_chest,
                line_comment=line_comment,
            )
        ),
        None,
    )
    new_qty = (existing.quantity if existing else 0) + qty
    if new_qty > variant.stock_quantity:
        left = variant.stock_quantity - (existing.quantity if existing else 0)
        if left <= 0:
            return _error("You already have all remaining stock of this size in your bag.")
        return _error(f"Only {left} left in this size.")

    if existing:
        existing.quantity = new_qty
        if save_measurement:
            existing.save_measurement = True
        line = existing
    else:
        line = CartItem(
            cart_id=cart.id,
            product_variant_id=variant.id,
            quantity=qty,
            is_custom=is_custom,
            custom_length=custom_length,
            custom_chest=custom_chest,
            line_comment=line_comment,
            save_measurement=save_measurement,
        )
        db.add(line)
        cart.items.append(line)

    customer = get_current_customer(request, db)
    if customer is not None and save_measurement and is_custom:
        save_customer_measurement(
            db,
            customer,
            length=custom_length or "",
            chest=custom_chest or "",
        )

    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    line = next(
        (
            item
            for item in cart.items
            if _item_matches(
                item,
                variant_id=variant.id,
                is_custom=is_custom,
                custom_length=custom_length,
                custom_chest=custom_chest,
                line_comment=line_comment,
            )
        ),
        line,
    )
    return _json(cart, token, needs_cookie, {"item": _item_info(line)})


@router.post("/cart/update", include_in_schema=False)
def cart_update(body: UpdateIn, request: Request, db: Session = Depends(get_db)):
    cart, token, needs_cookie = get_or_create_cart(db, request)
    item = next((row for row in cart.items if row.id == body.cart_item_id), None)
    if item is None:
        return _error("That item is not in your bag.", 404)
    if body.quantity == 0:
        db.delete(item)
        _touch(cart)
        db.commit()
        cart = reload_cart(db, cart.id)
        return _json(cart, token, needs_cookie)

    variant = item.variant
    if variant is None or body.quantity > variant.stock_quantity:
        stock = variant.stock_quantity if variant else 0
        return _error(f"Only {stock} left in this size.")
    item.quantity = body.quantity
    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    updated = next((row for row in cart.items if row.id == body.cart_item_id), None)
    extra = None
    if updated and updated.variant:
        extra = {
            "line": {
                "id": updated.id,
                "quantity": updated.quantity,
                "line_label": _fmt_bhd(_payable(updated.variant) * updated.quantity),
            }
        }
    return _json(cart, token, needs_cookie, extra)


@router.post("/cart/remove", include_in_schema=False)
def cart_remove(body: RemoveIn, request: Request, db: Session = Depends(get_db)):
    cart, token, needs_cookie = get_or_create_cart(db, request)
    item = next((row for row in cart.items if row.id == body.cart_item_id), None)
    if item is None:
        return _error("That item is not in your bag.", 404)
    undo = {
        "product_variant_id": item.product_variant_id,
        "quantity": item.quantity,
        "is_custom": bool(item.is_custom),
        "custom_length": item.custom_length or "",
        "custom_chest": item.custom_chest or "",
        "line_comment": item.line_comment or "",
        "save_measurement": bool(item.save_measurement),
    }
    db.delete(item)
    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    return _json(cart, token, needs_cookie, {"undo": undo})


@router.get("/cart/summary", include_in_schema=False)
def cart_summary(request: Request, db: Session = Depends(get_db)):
    cart, token, needs_cookie = get_or_create_cart(db, request)
    return _json(cart, token, needs_cookie)


@router.post("/cart/apply-code", include_in_schema=False)
def cart_apply_code(body: ApplyCodeIn, request: Request, db: Session = Depends(get_db)):
    cart, token, needs_cookie = get_or_create_cart(db, request)
    if not cart.items:
        return _error(GENERIC_INVALID)
    found = find_code(db, body.code)
    if not is_usable(found):
        return _error(GENERIC_INVALID)
    cart.discount_code_id = found.id
    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    return _json(cart, token, needs_cookie)


@router.post("/cart/remove-code", include_in_schema=False)
def cart_remove_code(request: Request, db: Session = Depends(get_db)):
    cart, token, needs_cookie = get_or_create_cart(db, request)
    cart.discount_code_id = None
    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    return _json(cart, token, needs_cookie)
