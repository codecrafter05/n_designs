from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.order import OrderItem


class Product(Base):
    """Catalog product. category_id must reference a leaf subcategory
    (Category.parent_id IS NOT NULL) — enforced in admin create/update.

    Pricing lives on ProductVariant, not here. Images are a shared gallery
    on this product (Product.images), not per color.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Deprecated: not the source of truth for what a product costs.
    # Use ProductVariant.price / compare_at_price. May be dropped in a later
    # migration once nothing reads this column.
    base_price: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    category: Mapped[Category] = relationship(back_populates="products")
    colors: Mapped[list[ProductColor]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )


class ProductColor(Base):
    __tablename__ = "product_colors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    color_name: Mapped[str] = mapped_column(String(100), nullable=False)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="colors")
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="color",
        cascade="all, delete-orphan",
    )


class ProductImage(Base):
    """Shared gallery image for a product (not per-color)."""

    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product: Mapped[Product] = relationship(back_populates="images")


class ProductVariant(Base):
    """Sellable SKU. Out of stock = stock_quantity 0; the row stays visible.

    `price` is the regular/normal price. `compare_at_price` is the optional
    discounted selling price (column name kept; UI label is "Discount").
    A variant is on sale when compare_at_price IS NOT NULL AND
    compare_at_price < price. Computed at query time — never stored separately.

    When on sale, compare_at_price is the payable price and price is the
    original shown struck through. When compare_at_price is empty, price
    is the payable price.
    """

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_color_id", "size", name="uq_product_color_size"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_color_id: Mapped[int] = mapped_column(
        ForeignKey("product_colors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    size: Mapped[str] = mapped_column(String(50), nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    compare_at_price: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)

    color: Mapped[ProductColor] = relationship(back_populates="variants")
    order_items: Mapped[list[OrderItem]] = relationship(back_populates="variant")
