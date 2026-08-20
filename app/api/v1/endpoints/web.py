import json
import logging
import os
from decimal import Decimal
from uuid import uuid4
from urllib.parse import quote, urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.cart import get_or_create_cart, set_cart_cookie
from app.core.config import Settings, settings
from app.core.customer_auth import create_customer_session, get_current_customer
from app.core.database import get_db
from app.core.discounts import REMOVED_AT_CHECKOUT, cart_pricing
from app.core.security import hash_password
from app.core.orders import (
    PAYMENT_COD,
    PAYMENT_TAP,
    SHIPPING_BHD,
    CheckoutBlocked,
    CheckoutDiscountGone,
    CheckoutFailed,
    CheckoutGone,
    as_money,
    finalize_order,
    form_from_session,
    fmt_bhd,
    order_number,
    plan_from_session,
    prepare_checkout,
)
from app.core.pricing import is_on_sale as _is_on_sale, payable as _payable
from app.core.site_content import (
    about_strip_images,
    about_values,
    get_site_settings,
    hero_slides,
    split_lines,
    split_paragraphs,
)
from app.core.tap import TAP_START_ERROR, TapError, create_charge, retrieve_charge, tap_configured
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.payment import PaymentSession
from app.models.product import Product, ProductColor, ProductVariant

logger = logging.getLogger(__name__)

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
COUNTRIES = (
    "Bahrain",
    "Saudi Arabia",
    "United Arab Emirates",
    "Kuwait",
    "Other",
)


def _fmt_bhd(amount) -> str:
    return fmt_bhd(amount)


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
    extra.setdefault("current_customer", None)
    return {
        "request": request,
        "nav_variant": nav_variant,
        "whatsapp_number": settings.contact_digits,
        "whatsapp_url": settings.whatsapp_url,
        "contact_phone": settings.contact_display,
        "contact_tel": settings.contact_tel,
        **extra,
    }


def _cart_count(cart) -> int:
    return sum(item.quantity for item in cart.items)


def _cart_lines(cart) -> tuple[list[dict], Decimal]:
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
    return lines, subtotal


def _promo_vars(cart) -> dict:
    pricing = cart_pricing(cart)
    return {
        "discount_code": pricing.discount_code,
        "discount_amount_label": _fmt_bhd(pricing.discount_amount),
        "discount_row_label": (
            f"Discount ({pricing.discount_code})" if pricing.discount_code else ""
        ),
        "cart_subtotal_label": _fmt_bhd(pricing.subtotal),
        "cart_payable_label": _fmt_bhd(pricing.payable_total),
        "cart_discount_amount": pricing.discount_amount,
        "cart_payable_total": pricing.payable_total,
        "cart_subtotal": pricing.subtotal,
    }


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
        extra.setdefault("current_customer", get_current_customer(request, db))
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
    site = get_site_settings(db)
    slides = hero_slides(db)
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
        hero_slides=slides,
        hero_heading_lines=split_lines(site.hero_heading if site else None),
    )


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def storefront_about(request: Request, db: Session = Depends(get_db)):
    site = get_site_settings(db)
    value_rows = about_values(db)
    return _storefront_page(
        request,
        "storefront/about.html",
        db=db,
        about_image_url=site.about_image_url if site else None,
        about_heading_lines=split_lines(site.about_heading if site else None),
        about_body_paragraphs=split_paragraphs(site.about_body if site else None),
        about_value_cards=[
            {
                "num": f"{index + 1:02d}",
                "heading": row.heading,
                "body": row.body,
            }
            for index, row in enumerate(value_rows)
        ],
        about_quote=(site.about_quote or "").strip() if site else "",
        about_cite=(site.about_cite or "").strip() if site else "",
        about_strip=about_strip_images(db),
    )


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
        f"{settings.whatsapp_url}"
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
    lines, _subtotal = _cart_lines(cart)
    promo = _promo_vars(cart)
    return _storefront_page(
        request,
        "storefront/cart.html",
        db=db,
        cart_lines=lines,
        **promo,
    )


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _checkout_form(data: dict | None = None) -> dict:
    data = data or {}
    return {
        "email": (data.get("email") or "").strip(),
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
        "address": (data.get("address") or "").strip(),
        "city": (data.get("city") or "").strip(),
        "country": (data.get("country") or "Bahrain").strip(),
        "phone": (data.get("phone") or "").strip(),
    }


def _form_from_customer(customer: Customer) -> dict:
    first, last = _split_name(customer.name)
    return _checkout_form(
        {
            "email": customer.email or "",
            "first_name": first,
            "last_name": last,
            "address": customer.address or "",
            "city": customer.city or "",
            "country": customer.country or "Bahrain",
            "phone": customer.phone or "",
        }
    )


def _checkout_page(
    request: Request,
    db: Session,
    *,
    form: dict | None = None,
    error: str | None = None,
    create_account: bool = False,
):
    cart, _, _ = get_or_create_cart(db, request)
    lines, _subtotal = _cart_lines(cart)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)
    customer = get_current_customer(request, db)
    if form is None and customer is not None:
        form = _form_from_customer(customer)
    shipping = SHIPPING_BHD
    promo = _promo_vars(cart)
    total = promo["cart_payable_total"] + shipping
    return _storefront_page(
        request,
        "storefront/checkout.html",
        db=db,
        cart_lines=lines,
        shipping_label=_fmt_bhd(shipping),
        checkout_total_label=_fmt_bhd(total),
        countries=COUNTRIES,
        form=_checkout_form(form),
        checkout_error=error,
        logged_in=customer is not None,
        create_account=create_account,
        **promo,
    )


def _payment_failed_redirect() -> RedirectResponse:
    return RedirectResponse(url="/checkout?payment_error=1", status_code=303)


def _start_tap_checkout(
    db: Session,
    prepared,
    form: dict,
    logged_in: Customer | None,
    want_account: bool,
    account_password: str,
) -> str | None:
    cart_id = prepared.cart.id
    items_json = json.dumps([line.as_json() for line in prepared.lines])
    token = uuid4().hex
    total = prepared.total
    subtotal = prepared.subtotal
    applied_discount = prepared.applied_discount
    discount_id = (
        prepared.discount_row.id if prepared.discount_row is not None else None
    )
    discount_code = (
        prepared.discount_row.code if prepared.discount_row is not None else None
    )
    customer_id = logged_in.id if logged_in is not None else None
    db.rollback()
    if not tap_configured():
        logger.warning("Tap start skipped; TAP_SECRET_KEY is not set")
        return None
    password_hash = hash_password(account_password) if want_account else None
    session = PaymentSession(
        token=token,
        status="pending",
        cart_id=cart_id,
        customer_id=customer_id,
        email=form["email"],
        first_name=form["first_name"],
        last_name=form["last_name"],
        phone=form["phone"],
        address=form["address"],
        city=form["city"],
        country=form["country"],
        shipping_address=f"{form['address']}, {form['city']}, {form['country']}",
        want_account=want_account,
        password_hash=password_hash,
        amount=total,
        currency="BHD",
        subtotal=subtotal,
        discount_code_id=discount_id,
        discount_amount=applied_discount if discount_id is not None else None,
        discount_code_snapshot=discount_code,
        items_json=items_json,
    )
    db.add(session)
    db.commit()
    site = (Settings().SITE_URL or "").rstrip("/")
    try:
        charge = create_charge(
            amount=total,
            currency="BHD",
            token=token,
            form=form,
            redirect_url=f"{site}/payment/callback/{token}",
            description="N Designs order",
        )
    except TapError:
        row = db.query(PaymentSession).filter(PaymentSession.token == token).first()
        if row is not None:
            db.delete(row)
            db.commit()
        return None
    charge_id = charge.get("id")
    pay_url = (charge.get("transaction") or {}).get("url")
    if not charge_id or not pay_url:
        logger.warning(
            "Tap create charge missing id/url session=%s charge=%s",
            token,
            charge_id,
        )
        row = db.query(PaymentSession).filter(PaymentSession.token == token).first()
        if row is not None:
            db.delete(row)
            db.commit()
        return None
    session = db.query(PaymentSession).filter(PaymentSession.token == token).first()
    if session is None:
        return None
    session.tap_charge_id = charge_id
    db.commit()
    logger.warning("Tap redirect session=%s charge=%s", token, charge_id)
    return pay_url


@router.get("/checkout/check-email", include_in_schema=False)
def checkout_check_email(email: str = "", db: Session = Depends(get_db)):
    email_key = email.strip().lower()
    if not email_key or "@" not in email_key:
        return JSONResponse({"exists": False})
    row = (
        db.query(Customer)
        .filter(func.lower(Customer.email) == email_key, Customer.hashed_password.isnot(None))
        .first()
    )
    return JSONResponse({"exists": row is not None})


@router.get("/checkout", response_class=HTMLResponse, include_in_schema=False)
def storefront_checkout(request: Request, db: Session = Depends(get_db)):
    error = None
    if request.query_params.get("payment_error") == "1":
        error = (
            "Payment was not completed — please try again or choose Cash on Delivery"
        )
    return _checkout_page(request, db, error=error)


@router.post("/checkout", include_in_schema=False)
def storefront_checkout_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    email: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    phone: str = Form(""),
    payment_method: str = Form("cod"),
    create_account: str = Form(""),
    account_password: str = Form(""),
):
    form = _checkout_form(
        {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "address": address,
            "city": city,
            "country": country,
            "phone": phone,
        }
    )
    logged_in = get_current_customer(request, db)
    want_account = create_account == "1" and logged_in is None

    def fail(message: str):
        return _checkout_page(
            request,
            db,
            form=form,
            error=message,
            create_account=want_account,
        )

    missing = [
        label
        for key, label in (
            ("email", "Email"),
            ("first_name", "First name"),
            ("last_name", "Last name"),
            ("address", "Address"),
            ("city", "City"),
            ("country", "Country"),
            ("phone", "Phone"),
        )
        if not form[key]
    ]
    if missing:
        return fail("Please fill in: " + ", ".join(missing) + ".")
    if "@" not in form["email"]:
        return fail("Please enter a valid email.")
    if payment_method not in ("cod", "online"):
        return fail("Please choose a payment method.")
    if want_account and len(account_password) < 8:
        return fail("Password must be at least 8 characters.")

    cart, _, _ = get_or_create_cart(db, request)
    lines, _subtotal = _cart_lines(cart)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)

    try:
        prepared = prepare_checkout(db, cart)
    except CheckoutGone:
        db.rollback()
        return RedirectResponse(url="/cart", status_code=303)
    except CheckoutDiscountGone:
        return fail(REMOVED_AT_CHECKOUT)
    except CheckoutBlocked as exc:
        db.rollback()
        return fail(exc.message)
    except Exception:
        db.rollback()
        return fail("Something went wrong, please try again.")

    if payment_method == "online":
        try:
            pay_url = _start_tap_checkout(
                db,
                prepared,
                form,
                logged_in,
                want_account,
                account_password,
            )
        except Exception:
            db.rollback()
            logger.warning("Tap checkout start failed", exc_info=True)
            return fail(TAP_START_ERROR)
        if not pay_url:
            return fail(TAP_START_ERROR)
        return RedirectResponse(url=pay_url, status_code=302)

    try:
        result = finalize_order(
            db,
            form=form,
            lines=prepared.lines,
            subtotal=prepared.subtotal,
            shipping=prepared.shipping,
            applied_discount=prepared.applied_discount,
            total=prepared.total,
            discount_row=prepared.discount_row,
            cart=prepared.cart,
            logged_in=logged_in,
            want_account=want_account,
            account_password=account_password,
            payment_method=PAYMENT_COD,
            background_tasks=background_tasks,
        )
    except CheckoutFailed as exc:
        db.rollback()
        return fail(exc.message)
    except CheckoutDiscountGone:
        db.rollback()
        return fail(REMOVED_AT_CHECKOUT)
    except CheckoutBlocked as exc:
        db.rollback()
        return fail(exc.message)
    except Exception:
        db.rollback()
        return fail("Something went wrong, please try again.")

    response = RedirectResponse(
        url=f"/order-confirmation/{result.order.id}", status_code=303
    )
    response.background = background_tasks
    if result.login_after and result.customer is not None:
        create_customer_session(response, db, result.customer)
    return response


@router.get(
    "/payment/callback/{token}",
    include_in_schema=False,
)
def payment_callback(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    tap_id: str = "",
):
    session = (
        db.query(PaymentSession).filter(PaymentSession.token == token).first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if session.status == "succeeded" and session.resulting_order_id:
        return RedirectResponse(
            url=f"/order-confirmation/{session.resulting_order_id}",
            status_code=303,
        )

    tap_id = (tap_id or request.query_params.get("tap_id") or "").strip()
    if not tap_id:
        logger.warning("Tap callback missing tap_id session=%s", token)
        session.status = "failed"
        db.commit()
        return _payment_failed_redirect()

    try:
        charge = retrieve_charge(tap_id)
    except TapError:
        logger.warning(
            "Tap retrieve failed session=%s tap_id=%s", token, tap_id
        )
        return _payment_failed_redirect()

    session = (
        db.query(PaymentSession)
        .filter(PaymentSession.token == token)
        .with_for_update()
        .first()
    )
    if session is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Not Found")
    if session.status == "succeeded" and session.resulting_order_id:
        order_id = session.resulting_order_id
        db.rollback()
        return RedirectResponse(
            url=f"/order-confirmation/{order_id}",
            status_code=303,
        )

    charge_id = str(charge.get("id") or "")
    logger.warning(
        "Tap callback session=%s charge=%s status=%s",
        token,
        charge_id,
        charge.get("status"),
    )
    if not session.tap_charge_id or charge_id != session.tap_charge_id:
        logger.warning(
            "Tap callback charge mismatch session=%s tap_id=%s stored=%s",
            token,
            charge_id,
            session.tap_charge_id,
        )
        session.status = "failed"
        db.commit()
        return _payment_failed_redirect()

    amount_ok = as_money(charge.get("amount")) == as_money(session.amount)
    currency_ok = str(charge.get("currency") or "").upper() == str(
        session.currency or "BHD"
    ).upper()
    if not amount_ok or not currency_ok:
        logger.warning(
            "Tap callback amount/currency mismatch session=%s charge=%s amount=%s/%s currency=%s/%s",
            token,
            charge_id,
            charge.get("amount"),
            session.amount,
            charge.get("currency"),
            session.currency,
        )
        session.status = "failed"
        db.commit()
        return _payment_failed_redirect()

    if str(charge.get("status") or "").upper() != "CAPTURED":
        session.status = "failed"
        db.commit()
        return _payment_failed_redirect()

    lines, cart, discount_row, logged_in = plan_from_session(db, session)
    form = form_from_session(session)
    try:
        result = finalize_order(
            db,
            form=form,
            lines=lines,
            subtotal=as_money(session.subtotal),
            shipping=SHIPPING_BHD,
            applied_discount=as_money(session.discount_amount),
            total=as_money(session.amount),
            discount_row=discount_row,
            cart=cart,
            logged_in=logged_in,
            want_account=bool(session.want_account),
            password_hash=session.password_hash,
            payment_method=PAYMENT_TAP,
            tap_charge_id=session.tap_charge_id,
            payment_session=session,
            lock_variants=True,
            honor_discount_snapshot=True,
            background_tasks=background_tasks,
        )
    except Exception:
        db.rollback()
        logger.warning(
            "Tap finalize failed session=%s charge=%s",
            token,
            charge_id,
            exc_info=True,
        )
        return _payment_failed_redirect()

    response = RedirectResponse(
        url=f"/order-confirmation/{result.order.id}", status_code=303
    )
    response.background = background_tasks
    if result.login_after and result.customer is not None:
        create_customer_session(response, db, result.customer)
    return response


@router.get(
    "/order-confirmation/{order_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def storefront_order_confirmation(
    order_id: int, request: Request, db: Session = Depends(get_db)
):
    order = (
        db.query(Order)
        .options(
            selectinload(Order.customer),
            selectinload(Order.discount_code),
            selectinload(Order.items)
            .selectinload(OrderItem.variant)
            .selectinload(ProductVariant.color)
            .selectinload(ProductColor.product)
            .selectinload(Product.images),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if order.customer_id is not None:
        viewer = get_current_customer(request, db)
        if viewer is None:
            return RedirectResponse(
                url="/login?"
                + urlencode({"next": f"/order-confirmation/{order.id}"}),
                status_code=303,
            )
        if viewer.id != order.customer_id:
            raise HTTPException(status_code=404, detail="Not Found")
    items = []
    for item in order.items:
        variant = item.variant
        color = variant.color if variant else None
        product = color.product if color else None
        items.append(
            {
                "name": product.name if product else "Item",
                "color": color.color_name if color else "",
                "size": variant.size if variant else "",
                "quantity": item.quantity,
                "line_label": _fmt_bhd(
                    Decimal(str(item.price_at_purchase)) * item.quantity
                ),
                "thumb": product.images[0].image_url if product and product.images else None,
            }
        )
    return _storefront_page(
        request,
        "storefront/order-confirmation.html",
        db=db,
        order=order,
        order_number=order_number(order.id),
        order_items=items,
        order_total_label=_fmt_bhd(order.total),
        order_subtotal_label=_fmt_bhd(
            sum(
                (
                    Decimal(str(item.price_at_purchase)) * item.quantity
                    for item in order.items
                ),
                Decimal("0"),
            )
        ),
        order_discount_code=order.discount_code_snapshot,
        order_discount_amount_label=(
            _fmt_bhd(order.discount_amount)
            if order.discount_code_snapshot
            else None
        ),
        order_shipping_label=_fmt_bhd(SHIPPING_BHD),
    )


@router.get("/terms", response_class=HTMLResponse, include_in_schema=False)
def storefront_terms(request: Request, db: Session = Depends(get_db)):
    return _storefront_page(request, "storefront/terms.html", db=db)


@router.get("/admin/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse("admin/dashboard/index.html", {"request": request})
