from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cart import Cart
    from app.models.order import Order


class DiscountCode(Base):
    """Percentage promo code. Codes are stored uppercase; uniqueness is case-insensitive.

    No delete: deactivate (`is_active=False`) to retire a code, same as Orders.
    `max_uses` NULL means unlimited. `times_used` is incremented in the order
    transaction so a failed checkout never counts.
    """

    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    times_used: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    applies_to_sale_items: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    carts: Mapped[list[Cart]] = relationship(back_populates="discount_code")
    orders: Mapped[list[Order]] = relationship(back_populates="discount_code")
