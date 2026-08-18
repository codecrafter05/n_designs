import os
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.v1.endpoints.web import _fmt_bhd
from app.core.database import get_db
from app.core.orders import SHIPPING_BHD, order_number
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductColor, ProductVariant

router = APIRouter(tags=["admin-orders"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))

STATUS_FILTERS = ("pending", "processing", "shipped", "delivered", "cancelled")
STATUS_LABELS = {
    "pending": "Pending",
    "processing": "Processing",
    "shipped": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
STATUS_BADGE = {
    "pending": "alert-admin-neutral",
    "processing": "alert-admin-progress",
    "shipped": "alert-admin-progress",
    "delivered": "alert-admin-success",
    "cancelled": "alert-admin-error",
}


def _redirect(path: str, **params: str) -> RedirectResponse:
    qs = urlencode({k: v for k, v in params.items() if v})
    url = f"{path}?{qs}" if qs else path
    return RedirectResponse(url=url, status_code=303)


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d %b %Y, %H:%M")


def _status_chip(status: str) -> dict:
    return {
        "status": status,
        "label": STATUS_LABELS.get(status, status.title()),
        "badge_class": STATUS_BADGE.get(status, "alert-admin-neutral"),
    }


def _order_load():
    return (
        selectinload(Order.customer),
        selectinload(Order.discount_code),
        selectinload(Order.items)
        .selectinload(OrderItem.variant)
        .selectinload(ProductVariant.color)
        .selectinload(ProductColor.product)
        .selectinload(Product.images),
    )


def _list_row(order: Order) -> dict:
    customer = order.customer
    chip = _status_chip(order.status)
    return {
        "id": order.id,
        "number": order_number(order.id),
        "customer_name": customer.name if customer else "—",
        "customer_email": customer.email if customer and customer.email else "—",
        "total_label": _fmt_bhd(order.total),
        "payment_method": order.payment_method,
        "placed_label": _fmt_dt(order.created_at),
        **chip,
    }


def _orders_href(*, customer_id: int | None = None, status: str | None = None) -> str:
    params: dict[str, str] = {}
    if customer_id is not None:
        params["customer_id"] = str(customer_id)
    if status:
        params["status"] = status
    qs = urlencode(params)
    return f"/admin/orders?{qs}" if qs else "/admin/orders"


@router.get("/admin/orders", response_class=HTMLResponse, include_in_schema=False)
def orders_list(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    customer_id: int | None = None,
):
    status_filter = (status or "").strip().lower()
    if status_filter and status_filter not in STATUS_FILTERS:
        return _redirect("/admin/orders", error="Unknown status filter.")

    customer = None
    if customer_id is not None:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if customer is None:
            return _redirect("/admin/orders", error="Customer not found.")

    count_query = db.query(Order.status, func.count(Order.id))
    if customer is not None:
        count_query = count_query.filter(Order.customer_id == customer.id)
    counts = {key: 0 for key in STATUS_FILTERS}
    for value, n in count_query.group_by(Order.status).all():
        if value in counts:
            counts[value] = n
    total_count = sum(counts.values())

    query = db.query(Order).options(selectinload(Order.customer))
    if customer is not None:
        query = query.filter(Order.customer_id == customer.id)
    if status_filter:
        query = query.filter(Order.status == status_filter)
    orders = query.order_by(Order.created_at.desc(), Order.id.desc()).all()

    cid = customer.id if customer is not None else None
    return templates.TemplateResponse(
        "admin/orders/index.html",
        {
            "request": request,
            "rows": [_list_row(order) for order in orders],
            "status_filter": status_filter,
            "customer": customer,
            "total_count": total_count,
            "filtered_count": len(orders),
            "counts": counts,
            "filters": [
                ("all", "All", total_count, _orders_href(customer_id=cid))
            ]
            + [
                (
                    key,
                    STATUS_LABELS[key],
                    counts[key],
                    _orders_href(customer_id=cid, status=key),
                )
                for key in STATUS_FILTERS
            ],
        },
    )


@router.get("/admin/orders/{order_id}", response_class=HTMLResponse, include_in_schema=False)
def orders_detail(order_id: int, request: Request, db: Session = Depends(get_db)):
    order = (
        db.query(Order)
        .options(*_order_load())
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        return _redirect("/admin/orders", error="Order not found.")

    items = []
    items_subtotal = Decimal("0")
    for item in order.items:
        variant = item.variant
        color = variant.color if variant else None
        product = color.product if color else None
        unit = Decimal(str(item.price_at_purchase))
        line = unit * item.quantity
        items_subtotal += line
        items.append(
            {
                "name": product.name if product else "Item",
                "color": color.color_name if color else "—",
                "size": variant.size if variant else "—",
                "quantity": item.quantity,
                "unit_label": _fmt_bhd(unit),
                "line_label": _fmt_bhd(line),
                "thumb": product.images[0].image_url if product and product.images else None,
            }
        )

    shipping = SHIPPING_BHD
    discount_amount = Decimal(str(order.discount_amount or 0))
    computed_total = items_subtotal - discount_amount + shipping
    stored_total = Decimal(str(order.total)).quantize(Decimal("0.001"))
    total_mismatch = computed_total.quantize(Decimal("0.001")) != stored_total

    return templates.TemplateResponse(
        "admin/orders/detail.html",
        {
            "request": request,
            "order": order,
            "number": order_number(order.id),
            "chip": _status_chip(order.status),
            "placed_label": _fmt_dt(order.created_at),
            "customer": order.customer,
            "items": items,
            "items_subtotal_label": _fmt_bhd(items_subtotal),
            "discount_code": order.discount_code.code if order.discount_code else None,
            "discount_amount_label": _fmt_bhd(discount_amount),
            "shipping_label": _fmt_bhd(shipping),
            "computed_total_label": _fmt_bhd(computed_total),
            "stored_total_label": _fmt_bhd(stored_total),
            "total_mismatch": total_mismatch,
            "statuses": [(key, STATUS_LABELS[key]) for key in STATUS_FILTERS],
        },
    )


@router.post("/admin/orders/{order_id}/status", include_in_schema=False)
def orders_update_status(
    order_id: int,
    status: str = Form(""),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        return _redirect("/admin/orders", error="Order not found.")
    new_status = status.strip().lower()
    if new_status not in STATUS_FILTERS:
        return _redirect(
            f"/admin/orders/{order_id}",
            error="Invalid status.",
        )
    order.status = new_status
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _redirect(f"/admin/orders/{order_id}", notice="Order status updated")
