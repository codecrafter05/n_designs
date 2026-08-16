import json
import os
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.cart import get_or_create_cart, set_cart_cookie
from app.core.config import settings
from app.core.database import get_db
from app.models.category import Category
from app.models.product import Product, ProductColor, ProductVariant

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


def homepage_featured_subcategories(db: Session) -> list[Category]:
    """Subcategories flagged for the homepage that have at least one active product.

    One query: EXISTS filter + correlated COUNT subquery. No N+1.
    """
    has_active_product = exists().where(
        Product.category_id == Category.id,
        Product.is_active.is_(True),
    )
    product_count = (
        select(func.count(Product.id))
        .where(Product.category_id == Category.id, Product.is_active.is_(True))
        .scalar_subquery()
        .label("product_count")
    )
    rows = (
        db.query(Category, product_count)
        .filter(
            Category.parent_id.isnot(None),
            Category.show_on_homepage.is_(True),
            has_active_product,
        )
        .order_by(Category.display_order, Category.id)
        .all()
    )
    categories = []
    for category, count in rows:
        category.product_count = count
        categories.append(category)
    return categories


def all_subcategories_with_counts(db: Session) -> list[Category]:
    """Every subcategory, with active product counts. Ordered by parent then display_order."""
    parent = aliased(Category)
    product_count = (
        select(func.count(Product.id))
        .where(Product.category_id == Category.id, Product.is_active.is_(True))
        .scalar_subquery()
        .label("product_count")
    )
    rows = (
        db.query(Category, product_count)
        .join(parent, Category.parent_id == parent.id)
        .options(selectinload(Category.parent))
        .filter(Category.parent_id.isnot(None))
        .order_by(parent.display_order, parent.id, Category.display_order, Category.id)
        .all()
    )
    categories = []
    for category, count in rows:
        category.product_count = count
        categories.append(category)
    return categories


def collections_grouped(db: Session) -> list[tuple[Category, list[Category]]]:
    """Subcategories grouped under their parent, parent order then display_order."""
    groups: list[tuple[Category, list[Category]]] = []
    index: dict[int, list[Category]] = {}
    for subcategory in all_subcategories_with_counts(db):
        parent = subcategory.parent
        if parent is None:
            continue
        children = index.get(parent.id)
        if children is None:
            children = []
            index[parent.id] = children
            groups.append((parent, children))
        children.append(subcategory)
    return groups


_TONES = ("a", "b", "c", "d")
NEW_ARRIVALS_LIMIT = 8
HOMEPAGE_SALE_LIMIT = 4


def _fmt_bhd(amount) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.001"))
    if value == value.to_integral():
        return f"BHD {int(value)}"
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"BHD {text}"


def _is_on_sale(variant: ProductVariant) -> bool:
    return (
        variant.compare_at_price is not None
        and variant.compare_at_price < variant.price
    )


def _payable(variant: ProductVariant) -> Decimal:
    if _is_on_sale(variant):
        return Decimal(str(variant.compare_at_price))
    return Decimal(str(variant.price))


def _product_query(db: Session):
    return db.query(Product).options(
        selectinload(Product.images),
        selectinload(Product.colors).selectinload(ProductColor.variants),
        selectinload(Product.category).selectinload(Category.parent),
    )


def _active_products(db: Session, limit: int | None = None) -> list[Product]:
    query = (
        _product_query(db)
        .filter(Product.is_active.is_(True))
        .order_by(Product.created_at.desc(), Product.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def _product_card(product: Product, index: int = 0) -> dict:
    variants = [variant for color in product.colors for variant in color.variants]
    payables = [_payable(variant) for variant in variants]
    regulars = [Decimal(str(variant.price)) for variant in variants]
    on_sale = any(_is_on_sale(variant) for variant in variants)
    if payables:
        low, high = min(payables), max(payables)
        price_label = (
            f"From {_fmt_bhd(low)}" if low != high else _fmt_bhd(low)
        )
        was_label = _fmt_bhd(min(regulars)) if on_sale and regulars else ""
    else:
        price_label = "—"
        was_label = ""
    colors = [color.color_name for color in product.colors if color.color_name]
    category = product.category
    parent = category.parent if category else None
    return {
        "slug": product.slug,
        "name": product.name,
        "thumb": product.images[0].image_url if product.images else None,
        "tag": parent.name if parent else (category.name if category else ""),
        "subcategory": category.name if category else "",
        "subcategory_slug": category.slug if category else "",
        "color_summary": " · ".join(colors),
        "price_label": price_label,
        "was_label": was_label,
        "on_sale": on_sale,
        "tone": _TONES[index % 4],
        "min_payable": min(payables) if payables else Decimal("0"),
    }


def _sale_products(db: Session, *, limit: int | None = None, random: bool = False) -> list[Product]:
    """Active products with at least one discounted variant. One EXISTS query, no N+1."""
    on_sale = exists().where(
        ProductColor.product_id == Product.id,
        ProductVariant.product_color_id == ProductColor.id,
        ProductVariant.compare_at_price.isnot(None),
        ProductVariant.compare_at_price < ProductVariant.price,
    )
    query = _product_query(db).filter(Product.is_active.is_(True), on_sale)
    if random:
        query = query.order_by(func.rand())
    else:
        query = query.order_by(Product.created_at.desc(), Product.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def _sale_card(product: Product, index: int = 0) -> dict:
    """Card prices use the deepest sale: lowest compare_at_price and that variant's regular price."""
    card = _product_card(product, index)
    sale_variants = [
        variant
        for color in product.colors
        for variant in color.variants
        if _is_on_sale(variant)
    ]
    if not sale_variants:
        return card
    best = min(sale_variants, key=lambda variant: Decimal(str(variant.compare_at_price)))
    card["price_label"] = _fmt_bhd(best.compare_at_price)
    card["was_label"] = _fmt_bhd(best.price)
    card["on_sale"] = True
    card["min_payable"] = Decimal(str(best.compare_at_price))
    return card


def _pdp_payload(product: Product) -> str:
    colors = []
    for color in product.colors:
        variants = []
        for variant in color.variants:
            on_sale = _is_on_sale(variant)
            variants.append(
                {
                    "id": variant.id,
                    "size": variant.size,
                    "stock": variant.stock_quantity,
                    "current_label": _fmt_bhd(_payable(variant)),
                    "was_label": _fmt_bhd(variant.price) if on_sale else None,
                }
            )
        colors.append(
            {
                "id": color.id,
                "name": color.color_name,
                "hex": color.color_hex or "#2b2b2f",
                "variants": variants,
            }
        )
    return json.dumps({"colors": colors})


def storefront_context(request: Request, *, nav_variant: str = "solid", **extra):
    extra.setdefault("footer_categories", extra.get("top_categories") or [])
    extra.setdefault("top_categories", [])
    extra.setdefault("cart_count", 0)
    return {
        "request": request,
        "nav_variant": nav_variant,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "whatsapp_url": f"https://wa.me/{settings.WHATSAPP_NUMBER}",
        **extra,
    }


def _cart_count(cart) -> int:
    return sum(item.quantity for item in cart.items)


def _cart_lines(cart) -> tuple[list[dict], str]:
    lines = []
    subtotal = Decimal("0")
    for item in cart.items:
        variant = item.variant
        if variant is None or variant.color is None or variant.color.product is None:
            continue
        product = variant.color.product
        payable = _payable(variant)
        on_sale = _is_on_sale(variant)
        line_total = payable * item.quantity
        subtotal += line_total
        lines.append(
            {
                "id": item.id,
                "quantity": item.quantity,
                "stock": variant.stock_quantity,
                "name": product.name,
                "slug": product.slug,
                "color": variant.color.color_name,
                "size": variant.size,
                "thumb": product.images[0].image_url if product.images else None,
                "unit_label": _fmt_bhd(payable),
                "was_label": _fmt_bhd(variant.price) if on_sale else "",
                "line_label": _fmt_bhd(line_total),
                "on_sale": on_sale,
            }
        )
    return lines, _fmt_bhd(subtotal) if lines else _fmt_bhd(0)


def _storefront_page(
    request: Request,
    template: str,
    *,
    db: Session | None = None,
    nav_variant: str = "solid",
    **extra,
):
    needs_cookie = False
    token = None
    if db is not None:
        if "footer_categories" not in extra:
            extra["footer_categories"] = top_categories_with_child_counts(db)
        cart, token, needs_cookie = get_or_create_cart(db, request)
        extra.setdefault("cart_count", _cart_count(cart))
    response = templates.TemplateResponse(
        template,
        storefront_context(request, nav_variant=nav_variant, **extra),
    )
    if needs_cookie and token:
        set_cart_cookie(response, token)
    return response


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def storefront_home(request: Request, db: Session = Depends(get_db)):
    top_categories = top_categories_with_child_counts(db)
    spotlight_subcategories = homepage_featured_subcategories(db)
    products = _active_products(db, limit=NEW_ARRIVALS_LIMIT)
    featured = (
        _product_query(db)
        .filter(Product.is_active.is_(True), Product.is_featured.is_(True))
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(3)
        .all()
    )
    return _storefront_page(
        request,
        "storefront/index.html",
        db=db,
        nav_variant="hero",
        top_categories=top_categories,
        footer_categories=top_categories,
        spotlight_subcategories=spotlight_subcategories,
        featured_pieces=[_product_card(product, i) for i, product in enumerate(featured)],
        new_arrivals=[_product_card(product, i) for i, product in enumerate(products)],
        sale_preview=[
            _sale_card(product, i)
            for i, product in enumerate(
                _sale_products(db, limit=HOMEPAGE_SALE_LIMIT, random=True)
            )
        ],
    )


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def storefront_about(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/about.html", db=db)


@router.get("/sale", response_class=HTMLResponse, include_in_schema=False)
def storefront_sale(request: Request, db: Session = Depends(get_db)):
    products = _sale_products(db)
    return _storefront_page(
        request,
        "storefront/sale.html",
        db=db,
        cards=[_sale_card(product, i) for i, product in enumerate(products)],
    )


@router.get("/collections", response_class=HTMLResponse, include_in_schema=False)
def storefront_collections(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(
        request,
        "storefront/collections.html",
        db=db,
        collection_groups=collections_grouped(db),
    )


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
def storefront_products_index():
    return RedirectResponse(url="/categories", status_code=303)


@router.get("/products/{subcategory_slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront_products(request: Request, subcategory_slug: str, db: Session = Depends(get_db)):
    subcategory = (
        db.query(Category)
        .options(selectinload(Category.parent))
        .filter(Category.slug == subcategory_slug, Category.parent_id.isnot(None))
        .first()
    )
    if subcategory is None:
        raise HTTPException(status_code=404, detail="Not Found")

    products = (
        _product_query(db)
        .filter(Product.is_active.is_(True), Product.category_id == subcategory.id)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .all()
    )
    cards = [_product_card(product, i) for i, product in enumerate(products)]
    sort = request.query_params.get("sort") or "newest"
    if sort == "price-low":
        cards.sort(key=lambda card: card["min_payable"])
    elif sort == "price-high":
        cards.sort(key=lambda card: card["min_payable"], reverse=True)
    else:
        sort = "newest"

    return _storefront_page(
        request,
        "storefront/products.html",
        db=db,
        subcategory=subcategory,
        parent=subcategory.parent,
        cards=cards,
        sort=sort,
    )


@router.get("/product/{slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront_product(request: Request, slug: str, db: Session = Depends(get_db)):
    product = (
        _product_query(db)
        .filter(Product.slug == slug, Product.is_active.is_(True))
        .first()
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Not Found")
    category = product.category
    parent = category.parent if category else None
    ask_url = (
        f"https://wa.me/{settings.WHATSAPP_NUMBER}"
        f"?text={quote(f'Hi, I am interested in {product.name}')}"
    )
    return _storefront_page(
        request,
        "storefront/product.html",
        db=db,
        product=product,
        parent=parent,
        catalog_json=_pdp_payload(product),
        whatsapp_url=ask_url,
        available=any(color.variants for color in product.colors),
    )


@router.get("/cart", response_class=HTMLResponse, include_in_schema=False)
def storefront_cart(request: Request, db: Session = Depends(get_db)):
    cart, _, _ = get_or_create_cart(db, request)
    lines, subtotal_label = _cart_lines(cart)
    return _storefront_page(
        request,
        "storefront/cart.html",
        db=db,
        cart_lines=lines,
        cart_subtotal_label=subtotal_label,
    )


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


@router.get("/admin/orders", response_class=HTMLResponse, include_in_schema=False)
def orders_page(request: Request):
    return _section_page(request, "admin/orders/index.html", "Orders")


@router.get("/admin/customers", response_class=HTMLResponse, include_in_schema=False)
def customers_page(request: Request):
    return _section_page(request, "admin/customers/index.html", "Customers")


@router.get("/admin/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request):
    return _section_page(request, "admin/settings/index.html", "Settings")
