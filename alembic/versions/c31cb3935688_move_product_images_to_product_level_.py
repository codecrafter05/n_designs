"""move product images to product level, add variant pricing

Revision ID: c31cb3935688
Revises: 3f7bd62c27b6
Create Date: 2026-08-16 10:48:18.323263

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'c31cb3935688'
down_revision: Union[str, None] = '3f7bd62c27b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL DDL is non-transactional: a previous failed run already added
    # product_id before dying on DROP INDEX. Skip if the column is present.
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("product_images")}
    if "product_id" not in cols:
        op.add_column("product_images", sa.Column("product_id", sa.Integer(), nullable=False))

    # Drop the FK before the index it uses (MySQL error 1553 otherwise).
    op.drop_constraint("product_images_ibfk_1", "product_images", type_="foreignkey")
    op.drop_index("ix_product_images_product_color_id", table_name="product_images")
    op.drop_column("product_images", "product_color_id")

    op.create_index(op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False)
    op.create_foreign_key(
        "fk_product_images_product_id",
        "product_images",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("product_variants", sa.Column("price", sa.Numeric(precision=12, scale=3), nullable=False))
    op.add_column("product_variants", sa.Column("compare_at_price", sa.Numeric(precision=12, scale=3), nullable=True))


def downgrade() -> None:
    op.drop_column("product_variants", "compare_at_price")
    op.drop_column("product_variants", "price")

    op.add_column("product_images", sa.Column("product_color_id", mysql.INTEGER(), autoincrement=False, nullable=False))
    op.drop_constraint("fk_product_images_product_id", "product_images", type_="foreignkey")
    op.drop_index(op.f("ix_product_images_product_id"), table_name="product_images")
    op.drop_column("product_images", "product_id")

    op.create_index("ix_product_images_product_color_id", "product_images", ["product_color_id"], unique=False)
    op.create_foreign_key(
        "product_images_ibfk_1",
        "product_images",
        "product_colors",
        ["product_color_id"],
        ["id"],
        ondelete="CASCADE",
    )
