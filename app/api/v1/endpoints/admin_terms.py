import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.site_content import (
    get_legal_page,
    get_or_create_legal_page,
    legal_body_for_editor,
    legal_html_or_none,
)
from app.models.site import TERMS_PAGE_SLUG

router = APIRouter(tags=["admin-terms"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))

ADMIN_TERMS_PATH = "/admin/Terms"
TITLE_MAX = 255


def _redirect(**params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{ADMIN_TERMS_PATH}?{qs}" if qs else ADMIN_TERMS_PATH
    return RedirectResponse(url=url, status_code=303)


def _blank(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _form_context(request: Request, db: Session) -> dict:
    page = get_legal_page(db, TERMS_PAGE_SLUG)
    return {
        "request": request,
        "page_title": "Terms",
        "page": page,
        "editor_html": legal_body_for_editor(page.body if page else None),
        "notice": request.query_params.get("notice"),
        "error": request.query_params.get("error"),
    }


@router.get("/admin/Terms", response_class=HTMLResponse, include_in_schema=False)
@router.get("/admin/terms", response_class=HTMLResponse, include_in_schema=False)
def terms_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "admin/terms/index.html",
        _form_context(request, db),
    )


@router.post("/admin/Terms", include_in_schema=False)
@router.post("/admin/terms", include_in_schema=False)
def terms_save(
    db: Session = Depends(get_db),
    title: str = Form(""),
    body: str = Form(""),
):
    heading = _blank(title)
    if heading and len(heading) > TITLE_MAX:
        return _redirect(error="Title must be 255 characters or fewer.")

    try:
        row = get_or_create_legal_page(db, TERMS_PAGE_SLUG)
        row.title = heading
        row.body = legal_html_or_none(body)
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        return _redirect(error="Could not save terms.")

    return _redirect(notice="Terms saved.")
