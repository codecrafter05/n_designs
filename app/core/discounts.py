from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.pricing import is_on_sale, payable
from app.models.cart import Cart
from app.models.discount import DiscountCode

GENERIC_INVALID = "This code is invalid or has expired"
REMOVED_AT_CHECKOUT = (
    "Your promo code is no longer valid and has been removed — "
    "please review your total before completing checkout"
)


def normalize_code(raw: str | None) -> str:
    return (raw or "").strip().upper()


def find_code(db: Session, raw: str | None) -> DiscountCode | None:
    key = normalize_code(raw)
    if not key:
        return None
    return (
        db.query(DiscountCode)
        .filter(func.upper(DiscountCode.code) == key)
        .first()
    )


def is_usable(code: DiscountCode | None) -> bool:
    if code is None or not code.is_active:
        return False
    if code.max_uses is not None and code.times_used >= code.max_uses:
        return False
    return True


def line_is_eligible(variant, applies_to_sale_items: bool) -> bool:
    if variant is None:
        return False
    if applies_to_sale_items:
        return True
    return not is_on_sale(variant)


def cart_subtotal(cart: Cart) -> Decimal:
    total = Decimal("0")
    for item in cart.items:
        if item.variant is None:
            continue
        total += payable(item.variant) * item.quantity
    return total.quantize(Decimal("0.001"))


def discount_amount(cart: Cart, code: DiscountCode | None) -> Decimal:
    if code is None:
        return Decimal("0.000")
    eligible = Decimal("0")
    for item in cart.items:
        variant = item.variant
        if variant is None:
            continue
        if line_is_eligible(variant, code.applies_to_sale_items):
            eligible += payable(variant) * item.quantity
    pct = Decimal(str(code.percentage)) / Decimal("100")
    return (eligible * pct).quantize(Decimal("0.001"))


@dataclass(frozen=True)
class CartPricing:
    subtotal: Decimal
    discount_amount: Decimal
    discount_code: str | None
    payable_total: Decimal


def cart_pricing(cart: Cart) -> CartPricing:
    subtotal = cart_subtotal(cart)
    code = cart.discount_code if cart.discount_code_id else None
    amount = discount_amount(cart, code) if code is not None else Decimal("0.000")
    return CartPricing(
        subtotal=subtotal,
        discount_amount=amount,
        discount_code=code.code if code is not None else None,
        payable_total=(subtotal - amount).quantize(Decimal("0.001")),
    )
