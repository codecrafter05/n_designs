from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cart import Cart
    from app.models.customer import Customer
    from app.models.discount import DiscountCode
    from app.models.order import Order


class PaymentSession(Base):
    """Pending Tap checkout. Order/stock/cart are untouched until the charge is CAPTURED."""

    STATUSES = ("pending", "succeeded", "failed")

    __tablename__ = "payment_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    cart_id: Mapped[int | None] = mapped_column(
        ForeignKey("carts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_address: Mapped[str] = mapped_column(Text, nullable=False)
    want_account: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BHD", nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    discount_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    discount_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    discount_code_snapshot: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    items_json: Mapped[str] = mapped_column(Text, nullable=False)
    tap_charge_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    resulting_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    cart: Mapped[Cart | None] = relationship()
    customer: Mapped[Customer | None] = relationship()
    discount_code: Mapped[DiscountCode | None] = relationship()
    resulting_order: Mapped[Order | None] = relationship()
