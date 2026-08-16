import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import router
from app.api.v1.endpoints.web import (
    router as web_router,
    storefront_context,
    templates,
    top_categories_with_child_counts,
)
from app.core.database import SessionLocal
from app.api.v1.endpoints.admin_categories import router as admin_categories_router
from app.api.v1.endpoints.admin_orders import router as admin_orders_router
from app.api.v1.endpoints.admin_products import router as admin_products_router
from app.api.v1.endpoints.cart import router as cart_router

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "template")
STOREFRONT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="N Designs",
    version="1.0.0",
    description="Clothing e-commerce backend for N Designs.",
    lifespan=lifespan,
)

# Serve template assets at /assets and /sass
app.mount("/assets", StaticFiles(directory=os.path.join(TEMPLATE_DIR, "assets")), name="assets")
app.mount("/sass", StaticFiles(directory=os.path.join(TEMPLATE_DIR, "sass")), name="sass")
app.mount("/static", StaticFiles(directory=STOREFRONT_STATIC_DIR), name="storefront_static")

# API routes
app.include_router(router)

# Web (HTML) routes — must come after static mounts
app.include_router(admin_categories_router)
app.include_router(admin_products_router)
app.include_router(admin_orders_router)
app.include_router(cart_router)
app.include_router(web_router)

_JSON_404_PREFIXES = ("/api", "/docs", "/redoc", "/assets", "/sass", "/static")


def _wants_json_404(path: str) -> bool:
    if path == "/openapi.json":
        return True
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _JSON_404_PREFIXES)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code != 404:
        return await http_exception_handler(request, exc)

    path = request.url.path
    if _wants_json_404(path):
        return JSONResponse({"detail": exc.detail}, status_code=404)
    if path.startswith("/admin"):
        return PlainTextResponse("Not Found", status_code=404)
    db = SessionLocal()
    try:
        footer_categories = top_categories_with_child_counts(db)
    finally:
        db.close()
    return templates.TemplateResponse(
        "storefront/404.html",
        storefront_context(
            request,
            nav_variant="solid",
            footer_categories=footer_categories,
        ),
        status_code=404,
    )
