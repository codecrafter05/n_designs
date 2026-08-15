import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["web"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)

templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def storefront_home(request: Request):
    return templates.TemplateResponse("storefront/index.html", {"request": request})


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


def _placeholder(request: Request, page_title: str):
    return templates.TemplateResponse(
        "dashboard-placeholder.html",
        {"request": request, "page_title": page_title},
    )


@router.get("/admin/dashboard/products", response_class=HTMLResponse, include_in_schema=False)
def products_page(request: Request):
    return _placeholder(request, "Products")


@router.get("/admin/dashboard/categories", response_class=HTMLResponse, include_in_schema=False)
def categories_page(request: Request):
    return _placeholder(request, "Categories")


@router.get("/admin/dashboard/orders", response_class=HTMLResponse, include_in_schema=False)
def orders_page(request: Request):
    return _placeholder(request, "Orders")


@router.get("/admin/dashboard/customers", response_class=HTMLResponse, include_in_schema=False)
def customers_page(request: Request):
    return _placeholder(request, "Customers")


@router.get("/admin/dashboard/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request):
    return _placeholder(request, "Settings")
