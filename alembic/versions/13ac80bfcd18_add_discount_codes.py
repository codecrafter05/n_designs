"""add discount codes

Revision ID: 13ac80bfcd18
Revises: e0d852c43a58
Create Date: 2026-08-18 22:32:39.669668

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "13ac80bfcd18"
down_revision: Union[str, None] = "e0d852c43a58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discount_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("percentage", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column(
            "times_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "applies_to_sale_items",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discount_codes_code"), "discount_codes", ["code"], unique=True
    )
    op.create_index(op.f("ix_discount_codes_id"), "discount_codes", ["id"], unique=False)

    op.add_column("carts", sa.Column("discount_code_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_carts_discount_code_id"), "carts", ["discount_code_id"], unique=False
    )
    op.create_foreign_key(
        "fk_carts_discount_code_id",
        "carts",
        "discount_codes",
        ["discount_code_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("orders", sa.Column("discount_code_id", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=3), nullable=True),
    )
    op.create_index(
        op.f("ix_orders_discount_code_id"),
        "orders",
        ["discount_code_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_orders_discount_code_id",
        "orders",
        "discount_codes",
        ["discount_code_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_discount_code_id", "orders", type_="foreignkey")
    op.drop_index(op.f("ix_orders_discount_code_id"), table_name="orders")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "discount_code_id")
    op.drop_constraint("fk_carts_discount_code_id", "carts", type_="foreignkey")
    op.drop_index(op.f("ix_carts_discount_code_id"), table_name="carts")
    op.drop_column("carts", "discount_code_id")
    op.drop_index(op.f("ix_discount_codes_id"), table_name="discount_codes")
    op.drop_index(op.f("ix_discount_codes_code"), table_name="discount_codes")
    op.drop_table("discount_codes")
