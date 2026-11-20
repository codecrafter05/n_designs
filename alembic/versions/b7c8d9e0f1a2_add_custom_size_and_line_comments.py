"""add custom size, line comments, and saved measurements

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-11-20 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_cart_item_variant", "cart_items", type_="unique")
    op.add_column(
        "cart_items",
        sa.Column(
            "is_custom",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "cart_items",
        sa.Column("custom_length", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "cart_items",
        sa.Column("custom_chest", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "cart_items",
        sa.Column("line_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "cart_items",
        sa.Column(
            "save_measurement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "order_items",
        sa.Column(
            "is_custom",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "order_items",
        sa.Column("custom_length", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("custom_chest", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("line_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("size_label", sa.String(length=120), nullable=True),
    )

    op.create_table(
        "customer_measurements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("length", sa.String(length=50), nullable=False),
        sa.Column("chest", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "length",
            "chest",
            name="uq_customer_measurement",
        ),
    )
    op.create_index(
        op.f("ix_customer_measurements_customer_id"),
        "customer_measurements",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_measurements_id"),
        "customer_measurements",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customer_measurements_id"), table_name="customer_measurements")
    op.drop_index(
        op.f("ix_customer_measurements_customer_id"),
        table_name="customer_measurements",
    )
    op.drop_table("customer_measurements")

    op.drop_column("order_items", "size_label")
    op.drop_column("order_items", "line_comment")
    op.drop_column("order_items", "custom_chest")
    op.drop_column("order_items", "custom_length")
    op.drop_column("order_items", "is_custom")

    op.drop_column("cart_items", "save_measurement")
    op.drop_column("cart_items", "line_comment")
    op.drop_column("cart_items", "custom_chest")
    op.drop_column("cart_items", "custom_length")
    op.drop_column("cart_items", "is_custom")
    op.create_unique_constraint(
        "uq_cart_item_variant", "cart_items", ["cart_id", "product_variant_id"]
    )
