from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.dial_codes import lookup_dial
from app.models.delivery import DeliveryGroup, DeliveryGroupCountry

MONEY = Decimal("0.001")
UNAVAILABLE_YET = (
    "Shipping to this destination isn't available yet — please contact us on WhatsApp"
)
UNKNOWN_DESTINATION = "We don't ship to this destination."


class ShippingUnavailable(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def as_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY)


def as_weight(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


def load_country_groups(db: Session) -> list[dict]:
    """Live shippable countries from Delivery Prices, for storefront selects."""
    groups = (
        db.query(DeliveryGroup)
        .options(selectinload(DeliveryGroup.countries))
        .filter(DeliveryGroup.is_active.is_(True))
        .order_by(DeliveryGroup.display_order, DeliveryGroup.id)
        .all()
    )
    out: list[dict] = []
    for group in groups:
        rows = sorted(group.countries, key=lambda c: c.country_name.lower())
        if not rows:
            continue
        countries = []
        for row in rows:
            dial = lookup_dial(row.country_name)
            countries.append(
                {
                    "name": row.country_name,
                    "dial_code": dial[0] if dial else "",
                    "flag": dial[1] if dial else "",
                }
            )
        out.append({"name": group.name, "countries": countries})
    return out


def flat_countries(groups: list[dict]) -> list[dict]:
    by_lower: dict[str, dict] = {}
    for group in groups:
        for country in group["countries"]:
            by_lower[country["name"].lower()] = country
    return sorted(by_lower.values(), key=lambda c: c["name"].lower())


def country_names(groups: list[dict]) -> list[str]:
    return [country["name"] for country in flat_countries(groups)]


def dial_options(groups: list[dict]) -> list[dict]:
    return [country for country in flat_countries(groups) if country.get("dial_code")]


def canonical_country_name(db: Session, country: str) -> str | None:
    name = (country or "").strip()
    if not name:
        return None
    row = (
        db.query(DeliveryGroupCountry)
        .filter(func.lower(DeliveryGroupCountry.country_name) == name.lower())
        .first()
    )
    return row.country_name if row is not None else None


def pick_country(preferred: str, names: list[str]) -> str:
    if not names:
        return (preferred or "").strip()
    by_lower = {name.lower(): name for name in names}
    key = (preferred or "").strip().lower()
    if key and key in by_lower:
        return by_lower[key]
    if "bahrain" in by_lower:
        return by_lower["bahrain"]
    return names[0]


def find_delivery_group(db: Session, country: str) -> DeliveryGroup | None:
    name = (country or "").strip()
    if not name:
        return None
    return (
        db.query(DeliveryGroup)
        .options(
            selectinload(DeliveryGroup.tiers),
            selectinload(DeliveryGroup.countries),
        )
        .join(DeliveryGroupCountry)
        .filter(func.lower(DeliveryGroupCountry.country_name) == name.lower())
        .first()
    )


def cart_weight_kg(cart) -> Decimal:
    """Sum of product.weight_kg * qty. NULL weight counts as 0."""
    total = Decimal("0")
    for item in cart.items:
        variant = item.variant
        product = variant.color.product if variant and variant.color else None
        weight = (
            as_weight(product.weight_kg)
            if product is not None and product.weight_kg is not None
            else Decimal("0")
        )
        total += weight * item.quantity
    return total.quantize(Decimal("0.001"))


def lines_weight_kg(lines, variants: dict) -> Decimal:
    total = Decimal("0")
    for line in lines:
        variant = variants.get(line.product_variant_id)
        product = None
        if variant is not None and variant.color is not None:
            product = variant.color.product
        weight = (
            as_weight(product.weight_kg)
            if product is not None and product.weight_kg is not None
            else Decimal("0")
        )
        total += weight * line.quantity
    return total.quantize(Decimal("0.001"))


def calculate_shipping(db: Session, country: str, cart_weight_kg: Decimal) -> Decimal:
    """Weight-based rate for this destination, plus handling fee, BHD 3dp.

    Raises ShippingUnavailable when the country has no group or no tiers.
    """
    group = find_delivery_group(db, country)
    if group is None:
        raise ShippingUnavailable(UNKNOWN_DESTINATION)
    if not group.is_active:
        raise ShippingUnavailable(UNAVAILABLE_YET)

    weight = as_weight(cart_weight_kg)
    if weight < 0:
        weight = Decimal("0")

    tiers = sorted(
        group.tiers,
        key=lambda row: (Decimal(str(row.max_weight_kg)), row.id),
    )
    if not tiers:
        raise ShippingUnavailable(UNAVAILABLE_YET)

    price: Decimal | None = None
    for tier in tiers:
        if weight <= Decimal(str(tier.max_weight_kg)):
            price = Decimal(str(tier.price))
            break

    if price is None:
        last = tiers[-1]
        last_w = Decimal(str(last.max_weight_kg))
        last_p = Decimal(str(last.price))
        if last_w <= 0:
            raise ShippingUnavailable(UNAVAILABLE_YET)
        if len(tiers) == 1:
            per_kg = last_p / last_w
        else:
            prev = tiers[-2]
            prev_w = Decimal(str(prev.max_weight_kg))
            prev_p = Decimal(str(prev.price))
            denom = last_w - prev_w
            if denom <= 0:
                per_kg = last_p / last_w
            else:
                per_kg = (last_p - prev_p) / denom
        price = last_p + (weight - last_w) * per_kg

    fee = Decimal(str(group.handling_fee or 0))
    return (price + fee).quantize(MONEY)
