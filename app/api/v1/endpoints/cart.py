from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.api.v1.endpoints.web import _fmt_bhd, _is_on_sale, _payable
from app.core.cart import get_or_create_cart, reload_cart, set_cart_cookie
from app.core.database import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product, ProductColor, ProductVariant

router = APIRouter(tags=["cart"])


class AddIn(BaseModel):
    product_variant_id: int
    quantity: int = 1


class UpdateIn(BaseModel):
    cart_item_id: int
    quantity: int = Field(..., ge=0)


class RemoveIn(BaseModel):
    cart_item_id: int


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)


def _payload(cart: Cart, extra: dict | None = None) -> dict:
    count = sum(item.quantity for item in cart.items)
    subtotal = Decimal("0")
    for item in cart.items:
        if item.variant is None:
            continue
        subtotal += _payable(item.variant) * item.quantity
    data = {
        "ok": True,
        "count": count,
        "subtotal_label": _fmt_bhd(subtotal) if count else _fmt_bhd(0),
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


def _item_info(item: CartItem) -> dict:
    variant = item.variant
    color = variant.color if variant else None
    product = color.product if color else None
    thumb = None
    if product and product.images:
        thumb = product.images[0].image_url
    return {
        "id": item.id,
        "product_variant_id": item.product_variant_id,
        "quantity": item.quantity,
        "name": product.name if product else "",
        "image": thumb,
        "color": color.color_name if color else "",
        "size": variant.size if variant else "",
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

    cart, token, needs_cookie = get_or_create_cart(db, request)
    existing = next(
        (item for item in cart.items if item.product_variant_id == variant.id),
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
        line = existing
    else:
        line = CartItem(cart_id=cart.id, product_variant_id=variant.id, quantity=qty)
        db.add(line)
        cart.items.append(line)
    _touch(cart)
    db.commit()
    cart = reload_cart(db, cart.id)
    line = next((item for item in cart.items if item.product_variant_id == variant.id), line)
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
