"""add legal pages

Revision ID: c8f21a9d4b70
Revises: 7e4a6733777f
Create Date: 2026-08-20 14:58:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f21a9d4b70"
down_revision: Union[str, Sequence[str], None] = "7e4a6733777f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TERMS_BODY = """Last updated August 2026

Orders & Payment

By placing an order with N Designs you confirm that the details provided are accurate and that you are authorised to use the selected payment method. Orders are confirmed once payment has been received in full.

Shipping

Orders within the Gulf typically arrive within 1–3 business days; international orders within 3–7 business days. Shipping costs are calculated at checkout based on destination and order weight.

- Bahrain: free shipping over BHD 30
- GCC: flat rate, shown at checkout
- International: calculated by destination

Returns & Exchanges

Unworn items with tags attached may be returned within 14 days of delivery for a refund or exchange. Occasion pieces marked as final sale are not eligible for return.

Sizing

Each product page includes a size guide with body measurements. If you are between sizes, we recommend sizing up for our relaxed-fit abayas and jalabiyas. For guidance, reach us on WhatsApp before ordering.

Privacy

We collect only the information needed to process and deliver your order. We do not sell customer data to third parties. Payment details are handled securely by our payment provider and are never stored on our servers.

Contact

For questions about these terms, call or WhatsApp us."""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "legal_pages" not in inspector.get_table_names():
        op.create_table(
            "legal_pages",
            sa.Column("slug", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("slug"),
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT slug FROM legal_pages WHERE slug = 'terms'")
    ).fetchone()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO legal_pages (slug, title, body, updated_at) "
                "VALUES (:slug, :title, :body, :updated_at)"
            ),
            {
                "slug": "terms",
                "title": "Terms & Conditions",
                "body": TERMS_BODY,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_table("legal_pages")
