import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.site_content import (
    about_strip_images,
    about_values,
    get_or_create_site_settings,
    get_site_settings,
    hero_slides,
)
from app.core.uploads import delete_image, save_image
from app.models.site import AboutStripImage, AboutValue, HeroSlide

router = APIRouter(tags=["admin-settings"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))

ABOUT_HEADING_MAX = 255
ABOUT_CITE_MAX = 255


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _blank(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _parse_gallery(raw: str, label: str = "Gallery") -> list[dict]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} data is invalid.") from exc
    if not isinstance(items, list):
        raise ValueError(f"{label} data is invalid.")
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{label} data is invalid.")
        if item.get("id"):
            parsed.append({"id": int(item["id"])})
        elif item.get("new") is not None:
            parsed.append({"new": int(item["new"])})
        else:
            raise ValueError(f"{label} data is invalid.")
    return parsed


def _parse_values(raw: str) -> list[dict]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Value cards data is invalid.") from exc
    if not isinstance(items, list):
        raise ValueError("Value cards data is invalid.")
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Value cards data is invalid.")
        heading = (item.get("heading") or "").strip()
        body = (item.get("body") or "").strip()
        if not heading and not body:
            continue
        if not heading or not body:
            raise ValueError("Each value card needs a heading and body.")
        if len(heading) > 255:
            raise ValueError("Value headings must be 255 characters or fewer.")
        entry = {"heading": heading, "body": body}
        if item.get("id"):
            entry["id"] = int(item["id"])
        parsed.append(entry)
    return parsed


def _gallery_dump(rows) -> str:
    return json.dumps([{"id": row.id, "url": row.image_url} for row in rows])


def _values_dump(rows: list[AboutValue]) -> str:
    return json.dumps(
        [{"id": row.id, "heading": row.heading, "body": row.body} for row in rows]
    )


def _form_context(request: Request, db: Session) -> dict:
    settings_row = get_site_settings(db)
    return {
        "request": request,
        "page_title": "Settings",
        "settings": settings_row,
        "gallery_json": _gallery_dump(hero_slides(db)),
        "strip_json": _gallery_dump(about_strip_images(db)),
        "values_json": _values_dump(about_values(db)),
        "notice": request.query_params.get("notice"),
        "error": request.query_params.get("error"),
    }


def _sync_image_rows(
    db: Session,
    model,
    gallery_items: list[dict],
    new_files: list[UploadFile],
    saved: list[str],
    kind: str,
    label: str,
) -> list[str]:
    pending_delete: list[str] = []
    existing = {row.id: row for row in db.query(model).all()}
    keep_ids = [item["id"] for item in gallery_items if "id" in item]
    for row_id, row in list(existing.items()):
        if row_id not in keep_ids:
            pending_delete.append(row.image_url)
            db.delete(row)
    db.flush()

    for index, item in enumerate(gallery_items):
        if "id" in item:
            row = existing.get(item["id"])
            if row is None:
                raise ValueError(f"An image in the {label} no longer exists.")
            row.sort_order = index
            continue
        file_index = item["new"]
        if file_index < 0 or file_index >= len(new_files):
            raise ValueError(f"A new {label} image is missing its file.")
        upload = new_files[file_index]
        if not upload.filename:
            raise ValueError(f"A new {label} image is missing its file.")
        url = save_image(upload, kind)
        saved.append(url)
        db.add(model(image_url=url, sort_order=index))
    return pending_delete


def _sync_values(db: Session, items: list[dict]) -> None:
    existing = {row.id: row for row in db.query(AboutValue).all()}
    keep_ids = [item["id"] for item in items if "id" in item]
    for row_id, row in list(existing.items()):
        if row_id not in keep_ids:
            db.delete(row)
    db.flush()
    for index, item in enumerate(items):
        if "id" in item:
            row = existing.get(item["id"])
            if row is None:
                raise ValueError("A value card no longer exists.")
            row.heading = item["heading"]
            row.body = item["body"]
            row.sort_order = index
            continue
        db.add(
            AboutValue(
                heading=item["heading"],
                body=item["body"],
                sort_order=index,
            )
        )


@router.get("/admin/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "admin/settings/index.html",
        _form_context(request, db),
    )


@router.post("/admin/settings", include_in_schema=False)
async def settings_save(
    request: Request,
    db: Session = Depends(get_db),
    hero_heading: str = Form(""),
    about_heading: str = Form(""),
    about_body: str = Form(""),
    about_quote: str = Form(""),
    about_cite: str = Form(""),
    gallery_json: str = Form("[]"),
    strip_json: str = Form("[]"),
    values_json: str = Form("[]"),
    about_clear_image: str = Form(""),
    about_image: UploadFile | None = File(None),
    new_images: list[UploadFile] | None = File(None),
    strip_images: list[UploadFile] | None = File(None),
):
    heading = _blank(hero_heading)
    about_title = _blank(about_heading)
    about_copy = _blank(about_body)
    quote = _blank(about_quote)
    cite = _blank(about_cite)
    if about_title and len(about_title) > ABOUT_HEADING_MAX:
        return _redirect(
            "/admin/settings",
            error="About heading must be 255 characters or fewer.",
        )
    if cite and len(cite) > ABOUT_CITE_MAX:
        return _redirect(
            "/admin/settings",
            error="Quote attribution must be 255 characters or fewer.",
        )

    try:
        gallery_items = _parse_gallery(gallery_json, "Hero")
        strip_items = _parse_gallery(strip_json, "About strip")
        value_items = _parse_values(values_json)
    except (ValueError, TypeError) as exc:
        return _redirect("/admin/settings", error=str(exc) or "Could not save settings.")

    new_files = [f for f in (new_images or []) if f is not None and f.filename]
    strip_files = [f for f in (strip_images or []) if f is not None and f.filename]
    saved_urls: list[str] = []
    pending_delete: list[str] = []
    about_saved: str | None = None

    try:
        row = get_or_create_site_settings(db)
        pending_delete.extend(
            _sync_image_rows(
                db, HeroSlide, gallery_items, new_files, saved_urls, "hero", "hero gallery"
            )
        )
        pending_delete.extend(
            _sync_image_rows(
                db,
                AboutStripImage,
                strip_items,
                strip_files,
                saved_urls,
                "about",
                "image strip",
            )
        )
        _sync_values(db, value_items)
        row.hero_heading = heading
        row.about_heading = about_title
        row.about_body = about_copy
        row.about_quote = quote
        row.about_cite = cite

        uploaded_about = about_image is not None and bool(about_image.filename)
        if uploaded_about:
            about_saved = save_image(about_image, "about")
            if row.about_image_url and row.about_image_url != about_saved:
                pending_delete.append(row.about_image_url)
            row.about_image_url = about_saved
        elif about_clear_image == "1" and row.about_image_url:
            pending_delete.append(row.about_image_url)
            row.about_image_url = None

        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        for url in saved_urls + ([about_saved] if about_saved else []):
            delete_image(url)
        return _redirect("/admin/settings", error=str(exc.detail))
    except ValueError as exc:
        db.rollback()
        for url in saved_urls + ([about_saved] if about_saved else []):
            delete_image(url)
        return _redirect("/admin/settings", error=str(exc))
    except Exception:
        db.rollback()
        for url in saved_urls + ([about_saved] if about_saved else []):
            delete_image(url)
        return _redirect("/admin/settings", error="Could not save settings.")

    for url in pending_delete:
        delete_image(url)
    return _redirect("/admin/settings", notice="Settings saved.")
