from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.product import Product


class Category(Base):
    """Product category tree (one table for both levels).

    Top-level categories (parent_id is NULL) only group subcategories
    (e.g. "Abayas"). Subcategories have parent_id set (e.g. "Everyday Abayas").

    Business rule (enforced later in application-layer validation, not by a
    DB constraint): Product.category_id must point at a subcategory
    (parent_id IS NOT NULL). Top-level categories never hold products.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Only meaningful for subcategories. Top-level rows stay False.
    show_on_homepage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    parent: Mapped[Category | None] = relationship(
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent",
        order_by="Category.display_order",
    )
    products: Mapped[list[Product]] = relationship(back_populates="category")
