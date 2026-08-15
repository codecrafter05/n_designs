import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.core.database import get_db
from app.models.category import Category

router = APIRouter(tags=["web"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


def top_categories_with_child_counts(db: Session) -> list[Category]:
    """Top-level categories that have at least one subcategory, plus a count.

    One query: EXISTS filter + correlated COUNT subquery. No N+1.
    """
    child = aliased(Category)
    subcategory_count = (
        select(func.count(child.id))
        .where(child.parent_id == Category.id)
        .scalar_subquery()
        .label("subcategory_count")
    )
    has_child = exists().where(child.parent_id == Category.id)
    rows = (
        db.query(Category, subcategory_count)
        .filter(Category.parent_id.is_(None), has_child)
        .order_by(Category.display_order, Category.id)
        .all()
    )
    categories = []
    for category, count in rows:
        category.subcategory_count = count
        categories.append(category)
    return categories


def storefront_context(request: Request, *, nav_variant: str = "solid", **extra):
    extra.setdefault("footer_categories", extra.get("top_categories") or [])
    extra.setdefault("top_categories", [])
    return {
        "request": request,
        "nav_variant": nav_variant,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "whatsapp_url": f"https://wa.me/{settings.WHATSAPP_NUMBER}",
        **extra,
    }


def _storefront_page(
    request: Request,
    template: str,
    *,
    db: Session | None = None,
    nav_variant: str = "solid",
    **extra,
):
    if "footer_categories" not in extra and db is not None:
        extra["footer_categories"] = top_categories_with_child_counts(db)
    return templates.TemplateResponse(
        template,
        storefront_context(request, nav_variant=nav_variant, **extra),
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def storefront_home(request: Request, db: Session = Depends(get_db)):
    top_categories = top_categories_with_child_counts(db)
    return _storefront_page(
        request,
        "storefront/index.html",
        db=db,
        nav_variant="hero",
        top_categories=top_categories,
        footer_categories=top_categories,
    )


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def storefront_about(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/about.html", db=db)


@router.get("/categories", response_class=HTMLResponse, include_in_schema=False)
def storefront_categories(request: Request, db: Session = Depends(get_db)):
    top_categories = top_categories_with_child_counts(db)
    return _storefront_page(
        request,
        "storefront/category.html",
        db=db,
        top_categories=top_categories,
        footer_categories=top_categories,
    )


@router.get("/categories/{slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront_category_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    category = (
        db.query(Category)
        .filter(Category.slug == slug, Category.parent_id.is_(None))
        .first()
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Not Found")
    subcategories = (
        db.query(Category)
        .filter(Category.parent_id == category.id)
        .order_by(Category.display_order, Category.id)
        .all()
    )
    return _storefront_page(
        request,
        "storefront/category.html",
        db=db,
        category=category,
        subcategories=subcategories,
    )


@router.get("/products", response_class=HTMLResponse, include_in_schema=False)
def storefront_products(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/products.html", db=db)


@router.get("/product/{slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront_product(request: Request, slug: str, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/product.html", db=db, slug=slug)


@router.get("/cart", response_class=HTMLResponse, include_in_schema=False)
def storefront_cart(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/cart.html", db=db)


@router.get("/checkout", response_class=HTMLResponse, include_in_schema=False)
def storefront_checkout(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/checkout.html", db=db)


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def storefront_terms(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/terms.html", db=db)


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse("admin/dashboard/index.html", {"request": request})


def _section_page(request: Request, template: str, page_title: str):
    return templates.TemplateResponse(
        template,
        {"request": request, "page_title": page_title},
    )


@router.get("/admin/dashboard/products", response_class=HTMLResponse, include_in_schema=False)
def products_page(request: Request):
    return _section_page(request, "admin/products/index.html", "Products")


@router.get("/admin/dashboard/orders", response_class=HTMLResponse, include_in_schema=False)
def orders_page(request: Request):
    return _section_page(request, "admin/orders/index.html", "Orders")


@router.get("/admin/dashboard/customers", response_class=HTMLResponse, include_in_schema=False)
def customers_page(request: Request):
    return _section_page(request, "admin/customers/index.html", "Customers")


@router.get("/admin/dashboard/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request):
    return _section_page(request, "admin/settings/index.html", "Settings")
