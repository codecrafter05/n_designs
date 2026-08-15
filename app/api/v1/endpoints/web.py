import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings

router = APIRouter(tags=["web"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


def storefront_context(request: Request, *, nav_variant: str = "solid", **extra):
    return {
        "request": request,
        "nav_variant": nav_variant,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "whatsapp_url": f"https://wa.me/{settings.WHATSAPP_NUMBER}",
        **extra,
    }


def _storefront_page(request: Request, template: str, *, nav_variant: str = "solid", **extra):
    return templates.TemplateResponse(
        template,
        storefront_context(request, nav_variant=nav_variant, **extra),
    )


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def storefront_home(request: Request):
    return _storefront_page(request, "storefront/index.html", nav_variant="hero")


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def storefront_about(request: Request):
    return _storefront_page(request, "storefront/about.html")


@router.get("/categories", response_class=HTMLResponse, include_in_schema=False)
def storefront_categories(request: Request):
    return _storefront_page(request, "storefront/category.html")


@router.get("/products", response_class=HTMLResponse, include_in_schema=False)
def storefront_products(request: Request):
    return _storefront_page(request, "storefront/products.html")


@router.get("/product/{slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront_product(request: Request, slug: str):
    return _storefront_page(request, "storefront/product.html", slug=slug)


@router.get("/cart", response_class=HTMLResponse, include_in_schema=False)
def storefront_cart(request: Request):
    return _storefront_page(request, "storefront/cart.html")


@router.get("/checkout", response_class=HTMLResponse, include_in_schema=False)
def storefront_checkout(request: Request):
    return _storefront_page(request, "storefront/checkout.html")


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def storefront_terms(request: Request):
    return _storefront_page(request, "storefront/terms.html")


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
