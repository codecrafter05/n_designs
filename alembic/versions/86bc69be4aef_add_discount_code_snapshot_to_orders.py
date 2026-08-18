"""add discount code snapshot to orders

Revision ID: 86bc69be4aef
Revises: 13ac80bfcd18
Create Date: 2026-08-18 23:22:08.413111

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "86bc69be4aef"
down_revision: Union[str, None] = "13ac80bfcd18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("discount_code_snapshot", sa.String(length=50), nullable=True),
    )
    # Best-effort backfill: copy the code's current name onto orders that used it.
    op.execute(
        """
        UPDATE orders AS o
        INNER JOIN discount_codes AS d ON d.id = o.discount_code_id
        SET o.discount_code_snapshot = d.code
        WHERE o.discount_code_id IS NOT NULL
          AND o.discount_code_snapshot IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("orders", "discount_code_snapshot")
