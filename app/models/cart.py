from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.discount import DiscountCode
    from app.models.product import ProductVariant


class Cart(Base):
    """Guest cart keyed by a cookie session token. No login required."""

    __tablename__ = "carts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    discount_code_id: Mapped[int | None] = mapped_column(
        ForeignKey("discount_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
    )
    discount_code: Mapped[DiscountCode | None] = relationship(
        back_populates="carts"
    )


class CartItem(Base):
    """One line in a cart. Custom sizes and comments keep separate lines."""

    __tablename__ = "cart_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cart_id: Mapped[int] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_custom: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    custom_length: Mapped[str | None] = mapped_column(String(50), nullable=True)
    custom_chest: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    save_measurement: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship(back_populates="cart_items")
