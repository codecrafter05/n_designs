from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DeliveryGroup(Base):
    """Named set of countries that share the same weight-based rates."""

    __tablename__ = "delivery_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    handling_fee: Mapped[float] = mapped_column(
        Numeric(12, 3), default=0, nullable=False
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    countries: Mapped[list[DeliveryGroupCountry]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    tiers: Mapped[list[DeliveryWeightTier]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class DeliveryGroupCountry(Base):
    __tablename__ = "delivery_group_countries"
    __table_args__ = (
        UniqueConstraint("country_name", name="uq_delivery_country_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)

    group: Mapped[DeliveryGroup] = relationship(back_populates="countries")


class DeliveryWeightTier(Base):
    """Up to max_weight_kg costs price (BHD), before the group's handling fee."""

    __tablename__ = "delivery_weight_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    max_weight_kg: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)

    group: Mapped[DeliveryGroup] = relationship(back_populates="tiers")
