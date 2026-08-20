"""add payment sessions and tap charge id

Revision ID: ac0e45a5a563
Revises: 86bc69be4aef
Create Date: 2026-08-19 14:32:37.351385

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "ac0e45a5a563"
down_revision: Union[str, None] = "86bc69be4aef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cart_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("shipping_address", sa.Text(), nullable=False),
        sa.Column(
            "want_account",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("discount_code_id", sa.Integer(), nullable=True),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("discount_code_snapshot", sa.String(length=50), nullable=True),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("tap_charge_id", sa.String(length=64), nullable=True),
        sa.Column("resulting_order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cart_id"], ["carts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["discount_code_id"], ["discount_codes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resulting_order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_sessions_cart_id"),
        "payment_sessions",
        ["cart_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_sessions_customer_id"),
        "payment_sessions",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_sessions_id"), "payment_sessions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_sessions_resulting_order_id"),
        "payment_sessions",
        ["resulting_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_sessions_tap_charge_id"),
        "payment_sessions",
        ["tap_charge_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_sessions_token"),
        "payment_sessions",
        ["token"],
        unique=True,
    )
    op.add_column(
        "orders", sa.Column("tap_charge_id", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_orders_tap_charge_id"), "orders", ["tap_charge_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_tap_charge_id"), table_name="orders")
    op.drop_column("orders", "tap_charge_id")
    op.drop_index(op.f("ix_payment_sessions_token"), table_name="payment_sessions")
    op.drop_index(
        op.f("ix_payment_sessions_tap_charge_id"), table_name="payment_sessions"
    )
    op.drop_index(
        op.f("ix_payment_sessions_resulting_order_id"),
        table_name="payment_sessions",
    )
    op.drop_index(op.f("ix_payment_sessions_id"), table_name="payment_sessions")
    op.drop_index(
        op.f("ix_payment_sessions_customer_id"), table_name="payment_sessions"
    )
    op.drop_index(
        op.f("ix_payment_sessions_cart_id"), table_name="payment_sessions"
    )
    op.drop_table("payment_sessions")
