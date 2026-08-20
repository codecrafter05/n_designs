from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SETTINGS_ROW_ID = 1


class SiteSettings(Base):
    """Singleton storefront copy. Application always reads/writes id=1."""

    __tablename__ = "site_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_site_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    hero_heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    about_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    about_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    about_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    about_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    about_cite: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class HeroSlide(Base):
    """Homepage hero image. One row = static; two or more = slideshow."""

    __tablename__ = "hero_slides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AboutValue(Base):
    """About page value card. Number label is derived from sort_order (01, 02, …)."""

    __tablename__ = "about_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    heading: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AboutStripImage(Base):
    """About page bottom image strip. Zero rows keep the placeholder tones."""

    __tablename__ = "about_strip_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
