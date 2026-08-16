import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.uploads import delete_image, save_image
from app.models.category import Category
from app.models.product import Product, ProductColor, ProductImage, ProductVariant

router = APIRouter(tags=["admin-products"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "product"


def _unique_slug(db: Session, name: str, exclude_id: int | None = None) -> str:
    base = _slugify(name)
    slug = base
    n = 2
    while True:
        q = db.query(Product).filter(Product.slug == slug)
        if exclude_id is not None:
            q = q.filter(Product.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def _subcategory_groups(db: Session) -> list[tuple[Category, list[Category]]]:
    parents = (
        db.query(Category)
        .filter(Category.parent_id.is_(None))
        .options(selectinload(Category.children))
        .order_by(Category.display_order, Category.id)
        .all()
    )
    groups = []
    for parent in parents:
        children = sorted(parent.children, key=lambda c: (c.display_order, c.id))
        if children:
            groups.append((parent, children))
    return groups


def _require_subcategory(db: Session, category_id: int) -> Category:
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None or category.parent_id is None:
        raise ValueError("Pick a subcategory — top-level categories cannot hold products.")
    return category


def _money(raw) -> Decimal:
    if raw is None or str(raw).strip() == "":
        raise ValueError("Price is required.")
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Price must be a number.") from exc
    if value <= 0:
        raise ValueError("Price must be greater than zero.")
    return value.quantize(Decimal("0.001"))


def _optional_compare(raw, price: Decimal) -> Decimal | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = Decimal(str(raw).strip()).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Discount must be a number.") from exc
    if value <= 0:
        raise ValueError("Discount must be greater than zero.")
    if value >= price:
        raise ValueError("Discount must be lower than the regular price.")
    return value


def _parse_inventory(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ValueError("Inventory data is invalid.") from exc
    colors = payload.get("colors") if isinstance(payload, dict) else None
    if not isinstance(colors, list) or not colors:
        raise ValueError("Add at least one color with a size.")

    parsed = []
    for color in colors:
        if not isinstance(color, dict):
            raise ValueError("Inventory data is invalid.")
        name = str(color.get("color_name") or "").strip()
        if not name:
            raise ValueError("Every color needs a name.")
        hex_value = str(color.get("color_hex") or "").strip() or None
        if hex_value and not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_value):
            raise ValueError("Color swatch must be a hex value like #2b2b2f.")
        variants_raw = color.get("variants")
        if not isinstance(variants_raw, list) or not variants_raw:
            raise ValueError(f"“{name}” needs at least one size.")
        variants = []
        seen_sizes: set[str] = set()
        for row in variants_raw:
            if not isinstance(row, dict):
                raise ValueError("Inventory data is invalid.")
            size = str(row.get("size") or "").strip()
            if not size:
                raise ValueError(f"Every size under “{name}” needs a label.")
            size_key = size.lower()
            if size_key in seen_sizes:
                raise ValueError(f"“{name}” has a duplicate size “{size}”.")
            seen_sizes.add(size_key)
            try:
                stock = int(row.get("stock_quantity") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("Quantity must be a whole number.") from exc
            if stock < 0:
                raise ValueError("Quantity cannot be negative.")
            price = _money(row.get("price"))
            compare = _optional_compare(row.get("compare_at_price"), price)
            variant_id = row.get("id")
            variants.append(
                {
                    "id": int(variant_id) if variant_id else None,
                    "size": size,
                    "stock_quantity": stock,
                    "price": price,
                    "compare_at_price": compare,
                }
            )
        color_id = color.get("id")
        parsed.append(
            {
                "id": int(color_id) if color_id else None,
                "color_name": name,
                "color_hex": hex_value,
                "variants": variants,
            }
        )
    return parsed


def _parse_gallery(raw: str) -> list[dict]:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Gallery data is invalid.") from exc
    if not isinstance(items, list):
        raise ValueError("Gallery data is invalid.")
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Gallery data is invalid.")
        if item.get("id"):
            parsed.append({"id": int(item["id"])})
        elif item.get("new") is not None:
            parsed.append({"new": int(item["new"])})
        else:
            raise ValueError("Gallery data is invalid.")
    return parsed


def _inventory_dump(product: Product | None) -> str:
    if product is None:
        return json.dumps({"colors": []})
    colors = []
    for color in product.colors:
        colors.append(
            {
                "id": color.id,
                "color_name": color.color_name,
                "color_hex": color.color_hex or "#2b2b2f",
                "variants": [
                    {
                        "id": variant.id,
                        "size": variant.size,
                        "stock_quantity": variant.stock_quantity,
                        "price": str(variant.price),
                        "compare_at_price": (
                            str(variant.compare_at_price)
                            if variant.compare_at_price is not None
                            else ""
                        ),
                    }
                    for variant in color.variants
                ],
            }
        )
    return json.dumps({"colors": colors})


def _gallery_dump(product: Product | None) -> str:
    if product is None:
        return "[]"
    return json.dumps(
        [{"id": image.id, "url": image.image_url} for image in product.images]
    )


def _sync_inventory(db: Session, product: Product, colors_data: list[dict]) -> Decimal:
    incoming_color_ids = {row["id"] for row in colors_data if row["id"]}
    for color in list(product.colors):
        if color.id not in incoming_color_ids:
            db.delete(color)
    db.flush()
    db.expire(product, ["colors"])

    color_by_id = {color.id: color for color in product.colors}
    min_price: Decimal | None = None
    for row in colors_data:
        color = color_by_id.get(row["id"]) if row["id"] else None
        if color is None:
            color = ProductColor(
                product_id=product.id,
                color_name=row["color_name"],
                color_hex=row["color_hex"],
            )
            db.add(color)
            db.flush()
        else:
            color.color_name = row["color_name"]
            color.color_hex = row["color_hex"]

        incoming_variant_ids = {item["id"] for item in row["variants"] if item["id"]}
        for variant in list(color.variants):
            if variant.id not in incoming_variant_ids:
                db.delete(variant)
        db.flush()
        db.expire(color, ["variants"])

        variant_by_id = {variant.id: variant for variant in color.variants}
        for item in row["variants"]:
            variant = variant_by_id.get(item["id"]) if item["id"] else None
            if variant is None:
                variant = ProductVariant(product_color_id=color.id)
                db.add(variant)
            variant.size = item["size"]
            variant.stock_quantity = item["stock_quantity"]
            variant.price = item["price"]
            variant.compare_at_price = item["compare_at_price"]
            if min_price is None or item["price"] < min_price:
                min_price = item["price"]
    return min_price or Decimal("0.000")


def _sync_gallery(
    db: Session,
    product: Product,
    gallery_items: list[dict],
    new_files: list[UploadFile],
    saved: list[str],
) -> list[str]:
    pending_delete: list[str] = []
    keep_ids = [item["id"] for item in gallery_items if "id" in item]
    for image in list(product.images):
        if image.id not in keep_ids:
            pending_delete.append(image.image_url)
            db.delete(image)
    db.flush()
    db.expire(product, ["images"])

    image_by_id = {image.id: image for image in product.images}
    for index, item in enumerate(gallery_items):
        if "id" in item:
            existing = image_by_id.get(item["id"])
            if existing is None:
                raise ValueError("An image in the gallery no longer exists.")
            existing.sort_order = index
            continue
        file_index = item["new"]
        if file_index < 0 or file_index >= len(new_files):
            raise ValueError("A new gallery image is missing its file.")
        upload = new_files[file_index]
        if not upload.filename:
            raise ValueError("A new gallery image is missing its file.")
        url = save_image(upload, "products")
        saved.append(url)
        db.add(
            ProductImage(product_id=product.id, image_url=url, sort_order=index)
        )
    return pending_delete


def _form_context(
    request: Request,
    db: Session,
    product: Product | None,
    extra: dict | None = None,
) -> dict:
    ctx = {
        "request": request,
        "product": product,
        "groups": _subcategory_groups(db),
        "inventory_json": _inventory_dump(product),
        "gallery_json": _gallery_dump(product),
        "error": request.query_params.get("error"),
    }
    if extra:
        ctx.update(extra)
    return ctx


def _summarize(product: Product) -> dict:
    variants = [variant for color in product.colors for variant in color.variants]
    prices = [Decimal(str(variant.price)) for variant in variants]
    if not prices:
        price_label = "—"
    elif min(prices) == max(prices):
        price_label = f"{min(prices):.3f}"
    else:
        price_label = f"{min(prices):.3f} – {max(prices):.3f}"
    category = product.category
    parent = category.parent if category else None
    if category and parent:
        category_label = f"{parent.name} → {category.name}"
    elif category:
        category_label = category.name
    else:
        category_label = "—"
    thumb = product.images[0].image_url if product.images else None
    on_sale = any(
        variant.compare_at_price is not None
        and variant.compare_at_price < variant.price
        for variant in variants
    )
    return {
        "product": product,
        "thumb": thumb,
        "category_label": category_label,
        "price_label": price_label,
        "stock": sum(variant.stock_quantity for variant in variants),
        "on_sale": on_sale,
    }


@router.get("/admin/products", response_class=HTMLResponse, include_in_schema=False)
def products_list(request: Request, db: Session = Depends(get_db)):
    products = (
        db.query(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.variants),
            selectinload(Product.category).selectinload(Category.parent),
        )
        .order_by(Product.created_at.desc(), Product.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/product/list.html",
        {
            "request": request,
            "rows": [_summarize(product) for product in products],
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/admin/products/new", response_class=HTMLResponse, include_in_schema=False)
def products_new(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        "admin/product/form.html",
        _form_context(request, db, None),
    )


@router.post("/admin/products", include_in_schema=False)
async def products_create(
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    is_active: str | None = Form(None),
    inventory_json: str = Form(...),
    gallery_json: str = Form("[]"),
    new_images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    return await _save_product(
        db,
        product=None,
        name=name,
        description=description,
        category_id=category_id,
        is_active=is_active,
        inventory_json=inventory_json,
        gallery_json=gallery_json,
        new_images=new_images,
        error_path="/admin/products/new",
    )


@router.get(
    "/admin/products/{product_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def products_edit(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = _load_product(db, product_id)
    if product is None:
        return _redirect("/admin/products", error="Product not found.")
    return templates.TemplateResponse(
        "admin/product/form.html",
        _form_context(request, db, product),
    )


@router.post("/admin/products/{product_id}/edit", include_in_schema=False)
async def products_update(
    product_id: int,
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    is_active: str | None = Form(None),
    inventory_json: str = Form(...),
    gallery_json: str = Form("[]"),
    new_images: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
):
    product = _load_product(db, product_id)
    if product is None:
        return _redirect("/admin/products", error="Product not found.")
    return await _save_product(
        db,
        product=product,
        name=name,
        description=description,
        category_id=category_id,
        is_active=is_active,
        inventory_json=inventory_json,
        gallery_json=gallery_json,
        new_images=new_images,
        error_path=f"/admin/products/{product_id}/edit",
    )


@router.post("/admin/products/{product_id}/toggle", include_in_schema=False)
def products_toggle(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        return _redirect("/admin/products", error="Product not found.")
    product.is_active = not product.is_active
    db.commit()
    state = "active" if product.is_active else "hidden"
    return _redirect("/admin/products", notice=f"Product marked {state}.")


@router.post("/admin/products/{product_id}/delete", include_in_schema=False)
def products_delete(product_id: int, db: Session = Depends(get_db)):
    product = _load_product(db, product_id)
    if product is None:
        return _redirect("/admin/products", error="Product not found.")
    image_urls = [image.image_url for image in product.images]
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        return _redirect(
            "/admin/products",
            error="Can't delete — this product is still referenced by an order.",
        )
    for url in image_urls:
        delete_image(url, "products")
    return _redirect("/admin/products", notice="Product deleted.")


def _load_product(db: Session, product_id: int) -> Product | None:
    return (
        db.query(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.colors).selectinload(ProductColor.variants),
        )
        .filter(Product.id == product_id)
        .first()
    )


async def _save_product(
    db: Session,
    *,
    product: Product | None,
    name: str,
    description: str | None,
    category_id: str,
    is_active: str | None,
    inventory_json: str,
    gallery_json: str,
    new_images: list[UploadFile],
    error_path: str,
):
    name = name.strip()
    if not name:
        return _redirect(error_path, error="Name is required.")
    try:
        resolved_category = _require_subcategory(db, int(category_id))
        colors_data = _parse_inventory(inventory_json)
        gallery_items = _parse_gallery(gallery_json)
    except (ValueError, TypeError) as exc:
        return _redirect(error_path, error=str(exc))

    is_create = product is None
    saved_urls: list[str] = []
    pending_delete: list[str] = []
    new_images = new_images or []
    try:
        if is_create:
            product = Product(
                name=name,
                slug=_unique_slug(db, name),
                description=(description or "").strip() or None,
                category_id=resolved_category.id,
                base_price=Decimal("0.000"),
                is_active=is_active == "1",
            )
            db.add(product)
            db.flush()
        else:
            product.name = name
            product.slug = _unique_slug(db, name, exclude_id=product.id)
            product.description = (description or "").strip() or None
            product.category_id = resolved_category.id
            product.is_active = is_active == "1"

        min_price = _sync_inventory(db, product, colors_data)
        product.base_price = min_price
        pending_delete = _sync_gallery(db, product, gallery_items, new_images, saved_urls)
        db.commit()
        for url in pending_delete:
            delete_image(url, "products")
    except ValueError as exc:
        db.rollback()
        for url in saved_urls:
            delete_image(url, "products")
        return _redirect(error_path, error=str(exc))
    except IntegrityError:
        db.rollback()
        for url in saved_urls:
            delete_image(url, "products")
        return _redirect(
            error_path,
            error="Couldn't save — a size may be duplicated, or a variant is still on an order.",
        )
    except HTTPException as exc:
        db.rollback()
        for url in saved_urls:
            delete_image(url, "products")
        return _redirect(error_path, error=str(exc.detail))
    except Exception:
        db.rollback()
        for url in saved_urls:
            delete_image(url, "products")
        return _redirect(error_path, error="Couldn't save this product. Try again.")

    notice = "Product created." if is_create else "Product updated."
    return _redirect("/admin/products", notice=notice)
