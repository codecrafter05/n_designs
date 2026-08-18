import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.customer import Customer
from app.models.order import Order

router = APIRouter(tags=["admin-customers"])

_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "views"))


def _list_row(customer: Customer, order_count: int) -> dict:
    registered = bool(customer.hashed_password)
    return {
        "id": customer.id,
        "name": customer.name or "—",
        "phone": customer.phone or "—",
        "country": customer.country or "—",
        "email": customer.email or "—",
        "order_count": order_count,
        "registered": registered,
        "account_label": "Registered" if registered else "Guest",
        "account_badge": "alert-admin-success" if registered else "alert-admin-neutral",
    }


@router.get("/admin/customers", response_class=HTMLResponse, include_in_schema=False)
def customers_list(request: Request, db: Session = Depends(get_db)):
    order_counts = (
        db.query(Order.customer_id, func.count(Order.id).label("order_count"))
        .filter(Order.customer_id.isnot(None))
        .group_by(Order.customer_id)
        .subquery()
    )
    count_col = func.coalesce(order_counts.c.order_count, 0)
    rows = (
        db.query(Customer, count_col)
        .outerjoin(order_counts, order_counts.c.customer_id == Customer.id)
        .order_by(count_col.desc(), Customer.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/customers/index.html",
        {
            "request": request,
            "rows": [_list_row(customer, int(count)) for customer, count in rows],
        },
    )
