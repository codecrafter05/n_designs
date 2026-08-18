from decimal import Decimal

from app.models.product import ProductVariant


def is_on_sale(variant: ProductVariant) -> bool:
    return (
        variant.compare_at_price is not None
        and variant.compare_at_price < variant.price
    )


def payable(variant: ProductVariant) -> Decimal:
    if is_on_sale(variant):
        return Decimal(str(variant.compare_at_price))
    return Decimal(str(variant.price))
