from decimal import Decimal

SHIPPING_BHD = Decimal("3.000")


def order_number(order_id: int) -> str:
    return f"ND-{int(order_id):05d}"
