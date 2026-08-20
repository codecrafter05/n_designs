from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.cart import reload_cart
from app.core.config import settings
from app.core.discounts import discount_amount, is_usable
from app.core.email import send_order_emails
from app.core.pricing import payable as _payable
from app.core.security import hash_password
from app.models.cart import Cart
from app.models.customer import Customer
from app.models.discount import DiscountCode
from app.models.order import Order, OrderItem
from app.models.payment import PaymentSession
from app.models.product import ProductColor, ProductVariant

logger = logging.getLogger(__name__)

SHIPPING_BHD = Decimal("3.000")
PAYMENT_COD = "Cash on Delivery"
PAYMENT_TAP = "Card (Tap)"


class CheckoutGone(Exception):
    """Cart vanished mid-submit."""


class CheckoutDiscountGone(Exception):
    """Promo became invalid after apply; already removed and committed."""


class CheckoutBlocked(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CheckoutFailed(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def order_number(order_id: int) -> str:
    return f"ND-{int(order_id):05d}"


def fmt_bhd(amount) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.001"))
    if value == value.to_integral():
        return f"BHD {int(value)}"
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"BHD {text}"


def as_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


@dataclass
class LineSnap:
    product_variant_id: int
    quantity: int
    price_at_purchase: Decimal
    name: str
    color: str
    size: str

    def as_json(self) -> dict:
        return {
            "product_variant_id": self.product_variant_id,
            "quantity": self.quantity,
            "price_at_purchase": str(self.price_at_purchase),
            "name": self.name,
            "color": self.color,
            "size": self.size,
        }

    @property
    def line_total(self) -> Decimal:
        return (self.price_at_purchase * self.quantity).quantize(Decimal("0.001"))

    def email_line(self) -> dict:
        return {
            "name": self.name,
            "color": self.color,
            "size": self.size,
            "quantity": self.quantity,
            "line_label": fmt_bhd(self.line_total),
        }


@dataclass
class PreparedCheckout:
    cart: Cart
    lines: list[LineSnap]
    subtotal: Decimal
    shipping: Decimal
    discount_row: DiscountCode | None
    applied_discount: Decimal
    total: Decimal


@dataclass
class FinalizeResult:
    order: Order
    customer: Customer | None
    login_after: bool
    email_payload: dict[str, Any]
    form: dict = field(default_factory=dict)


def cart_problems(cart) -> list[str]:
    problems = []
    for item in cart.items:
        variant = item.variant
        product = variant.color.product if variant and variant.color else None
        name = product.name if product else "An item"
        detail = ""
        if variant and variant.color:
            detail = f" ({variant.color.color_name} · {variant.size})"
        if product is None or not product.is_active:
            problems.append(f"{name}{detail} is no longer available.")
            continue
        if variant.stock_quantity < item.quantity:
            problems.append(
                f"{name}{detail} only has {variant.stock_quantity} left — "
                f"you have {item.quantity} in your bag."
            )
    return problems


def snapshot_cart_lines(cart) -> tuple[list[LineSnap], Decimal]:
    lines = []
    subtotal = Decimal("0")
    for item in cart.items:
        variant = item.variant
        if variant is None or variant.color is None or variant.color.product is None:
            continue
        product = variant.color.product
        price = _payable(variant)
        lines.append(
            LineSnap(
                product_variant_id=variant.id,
                quantity=item.quantity,
                price_at_purchase=price,
                name=product.name,
                color=variant.color.color_name,
                size=variant.size,
            )
        )
        subtotal += price * item.quantity
    return lines, subtotal.quantize(Decimal("0.001"))


def lines_from_json(raw: str) -> list[LineSnap]:
    rows = json.loads(raw or "[]")
    lines = []
    for row in rows:
        lines.append(
            LineSnap(
                product_variant_id=int(row["product_variant_id"]),
                quantity=int(row["quantity"]),
                price_at_purchase=as_money(row["price_at_purchase"]),
                name=str(row.get("name") or "Item"),
                color=str(row.get("color") or ""),
                size=str(row.get("size") or ""),
            )
        )
    return lines


def checkout_form_dict(form: dict) -> dict:
    return {
        "email": (form.get("email") or "").strip().lower(),
        "first_name": (form.get("first_name") or "").strip(),
        "last_name": (form.get("last_name") or "").strip(),
        "address": (form.get("address") or "").strip(),
        "city": (form.get("city") or "").strip(),
        "country": (form.get("country") or "Bahrain").strip(),
        "phone": (form.get("phone") or "").strip(),
    }


def form_from_session(session: PaymentSession) -> dict:
    return checkout_form_dict(
        {
            "email": session.email,
            "first_name": session.first_name,
            "last_name": session.last_name,
            "address": session.address,
            "city": session.city,
            "country": session.country,
            "phone": session.phone,
        }
    )


def apply_checkout_profile(customer: Customer, form: dict) -> None:
    customer.name = f"{form['first_name']} {form['last_name']}".strip()
    customer.email = form["email"].lower()
    customer.phone = form["phone"]
    customer.address = form["address"]
    customer.city = form["city"]
    customer.country = form["country"]


def order_email_payload(
    order: Order,
    form: dict,
    lines: list[LineSnap],
    subtotal,
    shipping,
    applied_discount,
    total,
) -> dict:
    discount_code = order.discount_code_snapshot
    placed = order.created_at
    site = (settings.SITE_URL or "").rstrip("/")
    return {
        "order_id": order.id,
        "order_number": order_number(order.id),
        "order_date": placed.strftime("%d %b %Y") if placed else "",
        "customer_name": f"{form['first_name']} {form['last_name']}".strip(),
        "customer_email": form["email"],
        "customer_phone": form["phone"],
        "shipping_address": order.shipping_address,
        "payment_method": order.payment_method,
        "items": [line.email_line() for line in lines],
        "subtotal_label": fmt_bhd(subtotal),
        "discount_code": discount_code,
        "discount_amount_label": (
            fmt_bhd(applied_discount) if discount_code else None
        ),
        "shipping_label": fmt_bhd(shipping),
        "total_label": fmt_bhd(total),
        "confirmation_url": f"{site}/order-confirmation/{order.id}",
        "admin_url": f"{site}/admin/orders/{order.id}",
    }


def prepare_checkout(db: Session, cart: Cart) -> PreparedCheckout:
    locked = (
        db.query(Cart).filter(Cart.id == cart.id).with_for_update().first()
    )
    if locked is None:
        raise CheckoutGone()
    cart = reload_cart(db, locked.id)
    variant_ids = sorted(
        {
            item.product_variant_id
            for item in cart.items
            if item.product_variant_id
        }
    )
    for variant_id in variant_ids:
        db.query(ProductVariant).filter(
            ProductVariant.id == variant_id
        ).with_for_update().first()
    cart = reload_cart(db, cart.id)
    if not cart.items:
        raise CheckoutGone()
    problems = cart_problems(cart)
    if problems:
        raise CheckoutBlocked(
            " ".join(problems) + " Update your bag and try again."
        )

    lines, subtotal = snapshot_cart_lines(cart)
    shipping = SHIPPING_BHD
    discount_row = None
    applied_discount = Decimal("0")
    if cart.discount_code_id:
        discount_row = (
            db.query(DiscountCode)
            .filter(DiscountCode.id == cart.discount_code_id)
            .with_for_update()
            .first()
        )
        if not is_usable(discount_row):
            cart.discount_code_id = None
            db.commit()
            raise CheckoutDiscountGone()
        applied_discount = discount_amount(cart, discount_row)
    total = subtotal - applied_discount + shipping
    return PreparedCheckout(
        cart=cart,
        lines=lines,
        subtotal=subtotal,
        shipping=shipping,
        discount_row=discount_row,
        applied_discount=applied_discount,
        total=total,
    )


def _lock_snapshot_variants(
    db: Session, lines: list[LineSnap]
) -> dict[int, ProductVariant]:
    variant_ids = sorted({line.product_variant_id for line in lines})
    locked: dict[int, ProductVariant] = {}
    for variant_id in variant_ids:
        row = (
            db.query(ProductVariant)
            .options(
                selectinload(ProductVariant.color).selectinload(ProductColor.product)
            )
            .filter(ProductVariant.id == variant_id)
            .with_for_update()
            .first()
        )
        if row is None:
            raise CheckoutBlocked("An item in this order is no longer available.")
        locked[variant_id] = row
    return locked


def _stock_problems_for_lines(
    lines: list[LineSnap], variants: dict[int, ProductVariant]
) -> list[str]:
    problems = []
    for line in lines:
        variant = variants.get(line.product_variant_id)
        product = variant.color.product if variant and variant.color else None
        name = product.name if product else line.name
        detail = ""
        if variant and variant.color:
            detail = f" ({variant.color.color_name} · {variant.size})"
        if product is None or not product.is_active:
            problems.append(f"{name}{detail} is no longer available.")
            continue
        if variant.stock_quantity < line.quantity:
            problems.append(
                f"{name}{detail} only has {variant.stock_quantity} left — "
                f"you have {line.quantity} in your bag."
            )
    return problems


def _resolve_customer(
    db: Session,
    form: dict,
    logged_in: Customer | None,
    want_account: bool,
    account_password: str,
    password_hash: str | None,
) -> tuple[Customer | None, bool]:
    login_after = False
    customer = None
    email_key = form["email"].lower()
    form["email"] = email_key
    hashed = password_hash
    if want_account and hashed is None and account_password:
        hashed = hash_password(account_password)

    if logged_in is not None:
        customer = db.query(Customer).filter(Customer.id == logged_in.id).first()
        if customer is None:
            raise CheckoutFailed("Something went wrong, please try again.")
        other = (
            db.query(Customer)
            .filter(
                func.lower(Customer.email) == email_key, Customer.id != customer.id
            )
            .first()
        )
        if other is not None:
            raise CheckoutFailed("This email is already in use")
        apply_checkout_profile(customer, form)
        return customer, False

    existing = (
        db.query(Customer).filter(func.lower(Customer.email) == email_key).first()
    )
    if existing is not None and existing.hashed_password:
        if want_account:
            raise CheckoutFailed(
                "An account with this email already exists — log in instead"
            )
        return None, False
    if existing is not None:
        customer = existing
        apply_checkout_profile(customer, form)
        if want_account:
            customer.hashed_password = hashed
            login_after = True
        return customer, login_after

    customer = Customer(
        name=f"{form['first_name']} {form['last_name']}".strip(),
        email=email_key,
        phone=form["phone"],
        address=form["address"],
        city=form["city"],
        country=form["country"],
        hashed_password=hashed if want_account else None,
    )
    db.add(customer)
    db.flush()
    return customer, bool(want_account)


def finalize_order(
    db: Session,
    *,
    form: dict,
    lines: list[LineSnap],
    subtotal: Decimal,
    shipping: Decimal,
    applied_discount: Decimal,
    total: Decimal,
    discount_row: DiscountCode | None,
    cart: Cart | None,
    logged_in: Customer | None,
    want_account: bool,
    account_password: str = "",
    password_hash: str | None = None,
    payment_method: str,
    tap_charge_id: str | None = None,
    payment_session: PaymentSession | None = None,
    lock_variants: bool = False,
    honor_discount_snapshot: bool = False,
    background_tasks: BackgroundTasks | None = None,
) -> FinalizeResult:
    """Create the Order, decrement stock, clear cart, increment discount usage.

    Does not touch the cart until this runs — Tap payments call this only after
    CAPTURED. Commits before queueing emails. When `payment_session` is passed,
    it is marked succeeded in the same commit.
    """
    if lock_variants:
        variants = _lock_snapshot_variants(db, lines)
        problems = _stock_problems_for_lines(lines, variants)
        if problems:
            raise CheckoutBlocked(
                " ".join(problems) + " Update your bag and try again."
            )
        if cart is not None and cart.id:
            locked_cart = (
                db.query(Cart).filter(Cart.id == cart.id).with_for_update().first()
            )
            cart = reload_cart(db, locked_cart.id) if locked_cart else None
    else:
        variants = {}
        for line in lines:
            row = (
                db.query(ProductVariant)
                .filter(ProductVariant.id == line.product_variant_id)
                .first()
            )
            if row is None:
                raise CheckoutBlocked("An item in this order is no longer available.")
            variants[line.product_variant_id] = row

    discount_code_id = None
    discount_code_snapshot = None
    discount_amount_value = None
    increment_row = None
    if honor_discount_snapshot and payment_session is not None:
        if payment_session.discount_code_snapshot:
            discount_code_snapshot = payment_session.discount_code_snapshot
            discount_amount_value = applied_discount
        if discount_row is not None:
            increment_row = (
                db.query(DiscountCode)
                .filter(DiscountCode.id == discount_row.id)
                .with_for_update()
                .first()
            )
            if increment_row is not None:
                discount_code_id = increment_row.id
    elif discount_row is not None:
        locked_code = (
            db.query(DiscountCode)
            .filter(DiscountCode.id == discount_row.id)
            .with_for_update()
            .first()
        )
        if not is_usable(locked_code):
            raise CheckoutDiscountGone()
        increment_row = locked_code
        discount_code_id = locked_code.id
        discount_code_snapshot = locked_code.code
        discount_amount_value = applied_discount

    customer, login_after = _resolve_customer(
        db,
        form,
        logged_in,
        want_account,
        account_password,
        password_hash,
    )
    shipping_address = f"{form['address']}, {form['city']}, {form['country']}"
    order = Order(
        customer_id=customer.id if customer is not None else None,
        status="pending",
        total=total,
        shipping_address=shipping_address,
        payment_method=payment_method,
        discount_code_id=discount_code_id,
        discount_amount=discount_amount_value,
        discount_code_snapshot=discount_code_snapshot,
        tap_charge_id=tap_charge_id,
    )
    db.add(order)
    db.flush()

    for line in lines:
        variant = variants[line.product_variant_id]
        db.add(
            OrderItem(
                order_id=order.id,
                product_variant_id=variant.id,
                quantity=line.quantity,
                price_at_purchase=line.price_at_purchase,
            )
        )
        variant.stock_quantity = variant.stock_quantity - line.quantity

    if increment_row is not None:
        increment_row.times_used = increment_row.times_used + 1

    if cart is not None:
        cart.discount_code_id = None
        for item in list(cart.items):
            db.delete(item)

    if payment_session is not None:
        payment_session.status = "succeeded"
        payment_session.resulting_order_id = order.id

    payload = order_email_payload(
        order,
        form,
        lines,
        subtotal,
        shipping,
        applied_discount,
        total,
    )
    db.commit()
    if background_tasks is not None:
        try:
            background_tasks.add_task(send_order_emails, payload)
        except Exception:
            logger.warning("Failed to queue order emails for order_id=%s", order.id)
    return FinalizeResult(
        order=order,
        customer=customer,
        login_after=login_after,
        email_payload=payload,
        form=form,
    )


def plan_from_session(
    db: Session, session: PaymentSession
) -> tuple[list[LineSnap], Cart | None, DiscountCode | None, Customer | None]:
    lines = lines_from_json(session.items_json)
    cart = reload_cart(db, session.cart_id) if session.cart_id else None
    discount_row = None
    if session.discount_code_id:
        discount_row = (
            db.query(DiscountCode)
            .filter(DiscountCode.id == session.discount_code_id)
            .first()
        )
    logged_in = None
    if session.customer_id:
        logged_in = (
            db.query(Customer).filter(Customer.id == session.customer_id).first()
        )
    return lines, cart, discount_row, logged_in
