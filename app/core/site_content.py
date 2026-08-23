from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser

from sqlalchemy.orm import Session

from app.core.slugs import slugify
from app.models.site import (
    SETTINGS_ROW_ID,
    AboutStripImage,
    AboutValue,
    HeroSlide,
    LegalPage,
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


def get_legal_page(db: Session, slug: str) -> LegalPage | None:
    return db.query(LegalPage).filter(LegalPage.slug == slug).first()


def get_or_create_legal_page(db: Session, slug: str) -> LegalPage:
    row = (
        db.query(LegalPage)
        .filter(LegalPage.slug == slug)
        .with_for_update()
        .first()
    )
    if row is None:
        row = LegalPage(slug=slug)
        db.add(row)
        db.flush()
    return row


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
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = []
    for block in normalized.split("\n\n"):
        lines = split_lines(block)
        if lines:
            blocks.append(lines)
    return blocks


_BULLET = re.compile(r"^[-*•]\s+")
_UPDATED = re.compile(r"^last updated\b", re.I)


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _is_heading(line: str) -> bool:
    if _is_bullet(line) or len(line) > 80:
        return False
    return line[-1:] not in ".!?"


def _heading_id(label: str, used: set[str]) -> str:
    slug = slugify(label, fallback="section")
    base = slug
    n = 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def parse_legal_body(text: str | None) -> dict:
    """Turn admin plain text into headings, paragraphs, and lists."""
    updated = None
    blocks: list[dict] = []
    toc: list[dict] = []
    used_ids: set[str] = set()

    raw_blocks = split_paragraphs(text)
    if raw_blocks and _UPDATED.match(raw_blocks[0][0]):
        updated = raw_blocks[0][0]
        rest = raw_blocks[0][1:]
        raw_blocks = ([rest] if rest else []) + raw_blocks[1:]

    def add_heading(label: str) -> None:
        section_id = _heading_id(label, used_ids)
        blocks.append({"type": "heading", "id": section_id, "text": label})
        toc.append({"id": section_id, "label": label})

    def add_paragraph(lines: list[str]) -> None:
        if lines:
            blocks.append({"type": "paragraph", "lines": lines})

    def add_list(entries: list[str]) -> None:
        if entries:
            blocks.append({"type": "list", "entries": entries})

    for group in raw_blocks:
        lines = list(group)
        if _is_heading(lines[0]):
            add_heading(lines[0])
            lines = lines[1:]

        para: list[str] = []
        items: list[str] = []
        for line in lines:
            if _is_bullet(line):
                add_paragraph(para)
                para = []
                items.append(_BULLET.sub("", line).strip())
                continue
            add_list(items)
            items = []
            para.append(line)
        add_paragraph(para)
        add_list(items)

    return {"updated": updated, "blocks": blocks, "toc": toc}


_VOID_TAGS = {"br"}
_SKIP_INNER = {"script", "style"}
_ALLOWED_TAGS = {
    "p": set(),
    "br": set(),
    "h2": {"id"},
    "h3": {"id"},
    "ul": set(),
    "ol": set(),
    "li": set(),
    "strong": set(),
    "em": set(),
    "b": set(),
    "i": set(),
    "u": set(),
    "a": {"href"},
}
_EMPTY_HTML = re.compile(r"<p>(?:\s|<br\s*/?>)*</p>", re.I)
_HEADING_TAG = re.compile(r"<(h[23])([^>]*)>(.*?)</\1>", re.I | re.S)
_FIRST_UPDATED_P = re.compile(
    r"^\s*<p>(Last updated[\s\S]*?)</p>", re.I
)
_TAG_TEXT = re.compile(r"<[^>]+>")


def _looks_like_html(text: str) -> bool:
    start = text.lstrip()
    return start.startswith("<") and ">" in start[:200]


def _safe_href(value: str) -> str | None:
    href = (value or "").strip()
    low = href.lower()
    if low.startswith(("javascript:", "data:", "vbscript:")):
        return None
    if low.startswith(("http://", "https://", "mailto:", "tel:", "/", "#")):
        return href
    return None


class _LegalSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._stack: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_INNER:
            self._skip += 1
            return
        if self._skip or tag not in _ALLOWED_TAGS:
            return
        kept: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name not in _ALLOWED_TAGS[tag]:
                continue
            if name == "href":
                value = _safe_href(value or "")
                if not value:
                    continue
            elif name == "id":
                value = slugify(value or "", fallback="")
                if not value:
                    continue
            kept.append(f'{name}="{escape(value, quote=True)}"')
        attr = (" " + " ".join(kept)) if kept else ""
        if tag in _VOID_TAGS:
            self.parts.append(f"<{tag}{attr}>")
            return
        self._stack.append(tag)
        self.parts.append(f"<{tag}{attr}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_INNER:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or tag in _VOID_TAGS or tag not in _ALLOWED_TAGS:
            return
        if tag not in self._stack:
            return
        while self._stack:
            top = self._stack.pop()
            self.parts.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        if data and not self._skip:
            self.parts.append(escape(data))


def sanitize_legal_html(html: str | None) -> str:
    parser = _LegalSanitizer()
    parser.feed(html or "")
    parser.close()
    while parser._stack:
        parser.parts.append(f"</{parser._stack.pop()}>")
    return _EMPTY_HTML.sub("", "".join(parser.parts)).strip()


def legal_html_or_none(html: str | None) -> str | None:
    cleaned = sanitize_legal_html(html)
    if not _TAG_TEXT.sub("", cleaned).strip():
        return None
    return cleaned


def _blocks_to_html(parsed: dict) -> str:
    parts: list[str] = []
    if parsed.get("updated"):
        parts.append(f"<p>{escape(parsed['updated'])}</p>")
    for block in parsed.get("blocks") or []:
        kind = block.get("type")
        if kind == "heading":
            parts.append(f"<h2>{escape(block['text'])}</h2>")
        elif kind == "paragraph":
            parts.append(
                "<p>" + "<br>".join(escape(line) for line in block["lines"]) + "</p>"
            )
        elif kind == "list":
            items = "".join(f"<li>{escape(entry)}</li>" for entry in block["entries"])
            parts.append(f"<ul>{items}</ul>")
    return "".join(parts)


def legal_body_for_editor(text: str | None) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if _looks_like_html(raw):
        return sanitize_legal_html(raw)
    return _blocks_to_html(parse_legal_body(raw))


def _decorate_legal_html(html: str) -> tuple[str, list[dict], str | None]:
    updated = None
    match = _FIRST_UPDATED_P.match(html)
    if match:
        updated = _TAG_TEXT.sub("", match.group(1)).strip() or None
        html = html[match.end() :].lstrip()

    toc: list[dict] = []
    used: set[str] = set()

    def repl(found: re.Match[str]) -> str:
        tag = found.group(1).lower()
        inner = found.group(3)
        label = unescape(_TAG_TEXT.sub("", inner)).strip()
        if not label:
            return found.group(0)
        existing = re.search(r'\bid="([^"]+)"', found.group(2) or "", re.I)
        section_id = existing.group(1) if existing else _heading_id(label, used)
        if existing:
            used.add(section_id)
        toc.append({"id": section_id, "label": label})
        return f'<{tag} id="{escape(section_id, quote=True)}">{inner}</{tag}>'

    html = _HEADING_TAG.sub(repl, html)
    return html, toc, updated


def prepare_legal_content(text: str | None) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {"html": "", "updated": None, "toc": []}
    if _looks_like_html(raw):
        html = sanitize_legal_html(raw)
    else:
        html = _blocks_to_html(parse_legal_body(raw))
    html, toc, updated = _decorate_legal_html(html)
    return {"html": html, "updated": updated, "toc": toc}
