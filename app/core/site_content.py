from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.site import (
    SETTINGS_ROW_ID,
    AboutStripImage,
    AboutValue,
    HeroSlide,
    SiteSettings,
)


def get_site_settings(db: Session) -> SiteSettings | None:
    return db.query(SiteSettings).filter(SiteSettings.id == SETTINGS_ROW_ID).first()


def get_or_create_site_settings(db: Session) -> SiteSettings:
    row = (
        db.query(SiteSettings)
        .filter(SiteSettings.id == SETTINGS_ROW_ID)
        .with_for_update()
        .first()
    )
    if row is None:
        row = SiteSettings(id=SETTINGS_ROW_ID)
        db.add(row)
        db.flush()
    return row


def hero_slides(db: Session) -> list[HeroSlide]:
    return (
        db.query(HeroSlide)
        .order_by(HeroSlide.sort_order, HeroSlide.id)
        .all()
    )


def about_values(db: Session) -> list[AboutValue]:
    return (
        db.query(AboutValue)
        .order_by(AboutValue.sort_order, AboutValue.id)
        .all()
    )


def about_strip_images(db: Session) -> list[AboutStripImage]:
    return (
        db.query(AboutStripImage)
        .order_by(AboutStripImage.sort_order, AboutStripImage.id)
        .all()
    )


def split_lines(text: str | None) -> list[str]:
    if not (text or "").strip():
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def split_paragraphs(text: str | None) -> list[list[str]]:
    if not (text or "").strip():
        return []
    blocks = []
    for block in text.strip().split("\n\n"):
        lines = split_lines(block.replace("\r\n", "\n"))
        if lines:
            blocks.append(lines)
    return blocks
