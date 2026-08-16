import re
import unicodedata

from sqlalchemy.orm import Session


def slugify(name: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or fallback


def unique_slug(db: Session, model, name: str, exclude_id: int | None = None) -> str:
    fallback = getattr(model, "__tablename__", "item").rstrip("s")
    base = slugify(name, fallback=fallback)
    slug = base
    n = 2
    while True:
        q = db.query(model).filter(model.slug == slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1
