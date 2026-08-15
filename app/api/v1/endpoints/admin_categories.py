import os
import re
import unicodedata
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.v1.endpoints.auth import _get_current_user
from app.core.database import get_db
from app.core.uploads import delete_category_image, save_category_image
from app.models.category import Category
from app.models.product import Product
from app.models.user import User

router = APIRouter(tags=["admin-categories"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


class ReorderPayload(BaseModel):
    parent_id: int | None = None
    ordered_ids: list[int]


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "category"


def _unique_slug(db: Session, name: str, exclude_id: int | None = None) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while True:
        q = db.query(Category).filter(Category.slug == slug)
        if exclude_id is not None:
            q = q.filter(Category.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _next_display_order(db: Session, parent_id: int | None) -> int:
    q = db.query(func.max(Category.display_order))
    if parent_id is None:
        q = q.filter(Category.parent_id.is_(None))
    else:
        q = q.filter(Category.parent_id == parent_id)
    current = q.scalar()
    return (current or 0) + 1


def _top_level(db: Session) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.parent_id.is_(None))
        .order_by(Category.display_order, Category.id)
        .all()
    )


def _resolve_parent(db: Session, parent_id: int | None) -> int | None:
    if parent_id is None:
        return None
    parent = db.query(Category).filter(Category.id == parent_id).first()
    if parent is None:
        raise HTTPException(status_code=400, detail="Parent category not found.")
    if parent.parent_id is not None:
        raise HTTPException(status_code=400, detail="Parent must be a top-level category.")
    return parent.id


def _parse_parent_id(raw: str | None) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


@router.get("/admin/dashboard/categories", response_class=HTMLResponse, include_in_schema=False)
def categories_list(request: Request, db: Session = Depends(get_db)):
    categories = (
        db.query(Category)
        .filter(Category.parent_id.is_(None))
        .options(selectinload(Category.children))
        .order_by(Category.display_order, Category.id)
        .all()
    )
    return templates.TemplateResponse(
        "admin/category/list.html",
        {
            "request": request,
            "categories": categories,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/admin/dashboard/categories/new", response_class=HTMLResponse, include_in_schema=False)
def categories_new(request: Request, db: Session = Depends(get_db), parent_id: int | None = None):
    return templates.TemplateResponse(
        "admin/category/form.html",
        {
            "request": request,
            "category": None,
            "parents": _top_level(db),
            "selected_parent_id": parent_id,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/dashboard/categories", include_in_schema=False)
async def categories_create(
    name: str = Form(...),
    parent_id: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return _redirect("/admin/dashboard/categories/new", error="Name is required.")
    try:
        resolved_parent = _resolve_parent(db, _parse_parent_id(parent_id))
    except (HTTPException, ValueError):
        return _redirect("/admin/dashboard/categories/new", error="Invalid parent category.")

    image_url = None
    if image is not None and image.filename:
        try:
            image_url = save_category_image(image)
        except HTTPException as exc:
            return _redirect("/admin/dashboard/categories/new", error=str(exc.detail))

    category = Category(
        name=name,
        slug=_unique_slug(db, name),
        parent_id=resolved_parent,
        image_url=image_url,
        display_order=_next_display_order(db, resolved_parent),
    )
    db.add(category)
    db.commit()
    return _redirect("/admin/dashboard/categories", notice="Category created.")


@router.get(
    "/admin/dashboard/categories/{category_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def categories_edit(category_id: int, request: Request, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        return _redirect("/admin/dashboard/categories", error="Category not found.")
    parents = [p for p in _top_level(db) if p.id != category.id]
    return templates.TemplateResponse(
        "admin/category/form.html",
        {
            "request": request,
            "category": category,
            "parents": parents,
            "selected_parent_id": category.parent_id,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/admin/dashboard/categories/reorder", include_in_schema=False)
def categories_reorder(
    payload: ReorderPayload,
    db: Session = Depends(get_db),
    _user: User = Depends(_get_current_user),
):
    if payload.parent_id is not None:
        parent = db.query(Category).filter(Category.id == payload.parent_id).first()
        if parent is None or parent.parent_id is not None:
            raise HTTPException(status_code=400, detail="Invalid parent group.")

    rows = (
        db.query(Category)
        .filter(
            Category.parent_id == payload.parent_id
            if payload.parent_id is not None
            else Category.parent_id.is_(None)
        )
        .all()
    )
    by_id = {row.id: row for row in rows}
    if set(payload.ordered_ids) != set(by_id.keys()):
        raise HTTPException(status_code=400, detail="Order list does not match this group.")

    for index, category_id in enumerate(payload.ordered_ids):
        by_id[category_id].display_order = index
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/admin/dashboard/categories/{category_id}", include_in_schema=False)
async def categories_update(
    category_id: int,
    name: str = Form(...),
    parent_id: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        return _redirect("/admin/dashboard/categories", error="Category not found.")

    name = name.strip()
    if not name:
        return _redirect(
            f"/admin/dashboard/categories/{category_id}/edit",
            error="Name is required.",
        )

    try:
        resolved_parent = _resolve_parent(db, _parse_parent_id(parent_id))
    except (HTTPException, ValueError):
        return _redirect(
            f"/admin/dashboard/categories/{category_id}/edit",
            error="Invalid parent category.",
        )

    if resolved_parent == category.id:
        return _redirect(
            f"/admin/dashboard/categories/{category_id}/edit",
            error="A category cannot be its own parent.",
        )

    if category.parent_id is None and resolved_parent is not None:
        child_count = (
            db.query(func.count(Category.id)).filter(Category.parent_id == category.id).scalar()
        )
        if child_count:
            return _redirect(
                f"/admin/dashboard/categories/{category_id}/edit",
                error="Move or remove subcategories before nesting this category.",
            )

    if image is not None and image.filename:
        try:
            new_url = save_category_image(image)
        except HTTPException as exc:
            return _redirect(
                f"/admin/dashboard/categories/{category_id}/edit",
                error=str(exc.detail),
            )
        delete_category_image(category.image_url)
        category.image_url = new_url

    if category.parent_id != resolved_parent:
        category.display_order = _next_display_order(db, resolved_parent)

    category.name = name
    category.slug = _unique_slug(db, name, exclude_id=category.id)
    category.parent_id = resolved_parent
    db.commit()
    return _redirect("/admin/dashboard/categories", notice="Category updated.")


@router.post("/admin/dashboard/categories/{category_id}/delete", include_in_schema=False)
def categories_delete(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        return _redirect("/admin/dashboard/categories", error="Category not found.")

    n_children = (
        db.query(func.count(Category.id)).filter(Category.parent_id == category.id).scalar() or 0
    )
    n_products = (
        db.query(func.count(Product.id)).filter(Product.category_id == category.id).scalar() or 0
    )
    if n_children or n_products:
        parts = []
        if n_children:
            parts.append(f"{n_children} subcategor{'ies' if n_children != 1 else 'y'}")
        if n_products:
            parts.append(f"{n_products} product{'s' if n_products != 1 else ''}")
        return _redirect(
            "/admin/dashboard/categories",
            error=f"Can't delete — this category still has {' / '.join(parts)}. Move or remove those first.",
        )

    image_url = category.image_url
    try:
        db.delete(category)
        db.commit()
    except IntegrityError:
        db.rollback()
        return _redirect(
            "/admin/dashboard/categories",
            error="Can't delete — this category still has related records. Move or remove those first.",
        )

    delete_category_image(image_url)
    return _redirect("/admin/dashboard/categories", notice="Category deleted.")
