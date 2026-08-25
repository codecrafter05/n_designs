"""Seed delivery groups, countries, and known weight tiers.

Safe to re-run: skips a group if its name already exists.

Usage:
    source .venv/bin/activate && python scripts/seed_delivery_prices.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app.core.database import SessionLocal
from app.models.delivery import DeliveryGroup, DeliveryGroupCountry, DeliveryWeightTier

GROUPS = (
    {
        "name": "Bahrain",
        "handling_fee": Decimal("0.000"),
        "display_order": 0,
        "countries": ("Bahrain",),
        "tiers": ((Decimal("9999"), Decimal("3.000")),),
    },
    {
        "name": "Gulf",
        "handling_fee": Decimal("1.000"),
        "display_order": 1,
        "countries": (
            "Saudi Arabia",
            "United Arab Emirates",
            "Kuwait",
            "Qatar",
            "Oman",
        ),
        "tiers": (
            (Decimal("0.5"), Decimal("3.500")),
            (Decimal("1"), Decimal("4.500")),
            (Decimal("1.5"), Decimal("6.000")),
            (Decimal("2"), Decimal("7.500")),
            (Decimal("2.5"), Decimal("8.000")),
            (Decimal("3"), Decimal("9.800")),
        ),
    },
    {
        "name": "USA & UK",
        "handling_fee": Decimal("1.000"),
        "display_order": 2,
        "countries": ("United States", "United Kingdom"),
        "tiers": (
            (Decimal("0.5"), Decimal("8.500")),
            (Decimal("1"), Decimal("15.500")),
            (Decimal("1.5"), Decimal("16.500")),
            (Decimal("2"), Decimal("22.500")),
            (Decimal("2.5"), Decimal("25.500")),
            (Decimal("3"), Decimal("30.500")),
        ),
    },
    {
        "name": "Jordan",
        "handling_fee": Decimal("1.000"),
        "display_order": 3,
        "countries": ("Jordan",),
        "tiers": (
            (Decimal("0.5"), Decimal("8.500")),
            (Decimal("1"), Decimal("13.500")),
            (Decimal("1.5"), Decimal("15.500")),
            (Decimal("2"), Decimal("22.500")),
            (Decimal("2.5"), Decimal("25.500")),
            (Decimal("3"), Decimal("28.500")),
        ),
    },
    {
        "name": "Australia",
        "handling_fee": Decimal("0.000"),
        "display_order": 4,
        "countries": ("Australia",),
        "tiers": (),
    },
    {
        "name": "Malaysia",
        "handling_fee": Decimal("0.000"),
        "display_order": 5,
        "countries": ("Malaysia",),
        "tiers": (),
    },
)


def seed(db) -> None:
    created = 0
    skipped = 0
    for spec in GROUPS:
        existing = (
            db.query(DeliveryGroup).filter(DeliveryGroup.name == spec["name"]).first()
        )
        if existing is not None:
            skipped += 1
            print(f"skip  {spec['name']} (already exists)")
            continue
        group = DeliveryGroup(
            name=spec["name"],
            handling_fee=spec["handling_fee"],
            display_order=spec["display_order"],
        )
        db.add(group)
        db.flush()
        for country in spec["countries"]:
            db.add(DeliveryGroupCountry(group_id=group.id, country_name=country))
        for max_kg, price in spec["tiers"]:
            db.add(
                DeliveryWeightTier(
                    group_id=group.id,
                    max_weight_kg=max_kg,
                    price=price,
                )
            )
        created += 1
        print(
            f"add   {spec['name']}: {len(spec['countries'])} countries, "
            f"{len(spec['tiers'])} tiers, handling {spec['handling_fee']}"
        )
    db.commit()
    print(f"done  created={created} skipped={skipped}")


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
