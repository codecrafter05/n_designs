from __future__ import annotations

from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy.orm import Session, selectinload

from app.models.cart import Cart, CartItem
from app.models.product import Product, ProductColor, ProductVariant

COOKIE_NAME = "cart_session"
COOKIE_MAX_AGE = 90 * 24 * 60 * 60


def _item_load():
    return (
        selectinload(Cart.items)
        .selectinload(CartItem.variant)
        .selectinload(ProductVariant.color)
        .selectinload(ProductColor.product)
        .selectinload(Product.images),
        selectinload(Cart.discount_code),
    )


def new_session_token() -> str:
    return uuid4().hex


def set_cart_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def get_or_create_cart(db: Session, request: Request) -> tuple[Cart, str, bool]:
    """Find or create the guest cart for this request. Never trusts a client cart_id."""
    token = request.cookies.get(COOKIE_NAME)
    needs_cookie = False
    if not token:
        token = new_session_token()
        needs_cookie = True

    cart = (
        db.query(Cart)
        .options(*_item_load())
        .filter(Cart.session_token == token)
        .first()
    )
    if cart is None:
        cart = Cart(session_token=token)
        db.add(cart)
        db.commit()
        cart = reload_cart(db, cart.id)
        needs_cookie = True
    return cart, token, needs_cookie


def reload_cart(db: Session, cart_id: int) -> Cart | None:
    return (
        db.query(Cart)
        .options(*_item_load())
        .filter(Cart.id == cart_id)
        .first()
    )
