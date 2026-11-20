"""Custom size labels and saved customer measurements."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.customer import Customer, CustomerMeasurement


def size_label(
    *,
    is_custom: bool = False,
    custom_length: str | None = None,
    custom_chest: str | None = None,
    variant_size: str | None = None,
    stored_label: str | None = None,
) -> str:
    if stored_label:
        return stored_label
    if is_custom:
        length = (custom_length or "").strip()
        chest = (custom_chest or "").strip()
        return f'Custom — Length {length}" / Chest {chest}"'
    return (variant_size or "").strip()


def normalize_inches(value: str | None) -> str:
    text = (value or "").strip()
    if text.endswith('"'):
        text = text[:-1].strip()
    return text


def save_customer_measurement(
    db: Session,
    customer: Customer,
    *,
    length: str,
    chest: str,
) -> CustomerMeasurement | None:
    length_key = normalize_inches(length)
    chest_key = normalize_inches(chest)
    if not length_key or not chest_key:
        return None
    existing = (
        db.query(CustomerMeasurement)
        .filter(
            CustomerMeasurement.customer_id == customer.id,
            CustomerMeasurement.length == length_key,
            CustomerMeasurement.chest == chest_key,
        )
        .first()
    )
    if existing is not None:
        return existing
    row = CustomerMeasurement(
        customer_id=customer.id,
        length=length_key,
        chest=chest_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    return row


def customer_measurements_payload(customer: Customer | None) -> list[dict]:
    if customer is None:
        return []
    rows = getattr(customer, "measurements", None) or []
    return [
        {
            "id": row.id,
            "length": row.length,
            "chest": row.chest,
            "label": size_label(
                is_custom=True,
                custom_length=row.length,
                custom_chest=row.chest,
            ),
        }
        for row in rows
    ]
