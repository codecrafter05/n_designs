"""add next-order account discount

Revision ID: a1b2c3d4e5f6
Revises: 642177c4fc15
Create Date: 2026-09-24 19:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "642177c4fc15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "next_order_discount",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "orders",
        sa.Column("account_discount_amount", sa.Numeric(12, 3), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "account_offer_granted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "payment_sessions",
        sa.Column("account_discount_amount", sa.Numeric(12, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_sessions", "account_discount_amount")
    op.drop_column("orders", "account_offer_granted")
    op.drop_column("orders", "account_discount_amount")
    op.drop_column("customers", "next_order_discount")
