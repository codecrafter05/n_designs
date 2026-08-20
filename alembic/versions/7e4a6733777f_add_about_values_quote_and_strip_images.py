"""add about values quote and strip images

Revision ID: 7e4a6733777f
Revises: 0906a0e750b4
Create Date: 2026-08-20 14:43:21.211874

"""
from datetime import datetime, timezone
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "7e4a6733777f"
down_revision: Union[str, None] = "0906a0e750b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


QUOTE = (
    "Quiet elegance isn't the absence of statement — "
    "it's a statement made once, well."
)
CITE = "Founder, N Designs"
VALUES = (
    (
        "Considered Fabric",
        "We work with brushed crepes, linen blends and matte satins chosen "
        "for how they move and travel, not just how they photograph.",
    ),
    (
        "Small Batches",
        "Every collection is produced in limited runs, cut and finished by "
        "hand in our Manama studio — never mass-produced.",
    ),
    (
        "Made to Travel",
        "Packed and shipped from Bahrain to the Gulf and internationally, "
        "with the same care whether you're two streets or two continents away.",
    ),
)


def upgrade() -> None:
    op.create_table(
        "about_strip_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_about_strip_images_id"),
        "about_strip_images",
        ["id"],
        unique=False,
    )
    op.create_table(
        "about_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_about_values_id"), "about_values", ["id"], unique=False
    )
    op.add_column("site_settings", sa.Column("about_quote", sa.Text(), nullable=True))
    op.add_column(
        "site_settings", sa.Column("about_cite", sa.String(length=255), nullable=True)
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM site_settings WHERE id = 1")
    ).fetchone()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO site_settings (id, about_quote, about_cite, updated_at) "
                "VALUES (1, :quote, :cite, :updated_at)"
            ),
            {"quote": QUOTE, "cite": CITE, "updated_at": now},
        )
    else:
        conn.execute(
            sa.text(
                "UPDATE site_settings "
                "SET about_quote = COALESCE(about_quote, :quote), "
                "    about_cite = COALESCE(about_cite, :cite) "
                "WHERE id = 1"
            ),
            {"quote": QUOTE, "cite": CITE},
        )
    value_count = conn.execute(sa.text("SELECT COUNT(*) FROM about_values")).scalar()
    if not value_count:
        for index, (heading, body) in enumerate(VALUES):
            conn.execute(
                sa.text(
                    "INSERT INTO about_values (heading, body, sort_order, created_at) "
                    "VALUES (:heading, :body, :sort_order, :created_at)"
                ),
                {
                    "heading": heading,
                    "body": body,
                    "sort_order": index,
                    "created_at": now,
                },
            )


def downgrade() -> None:
    op.drop_column("site_settings", "about_cite")
    op.drop_column("site_settings", "about_quote")
    op.drop_index(op.f("ix_about_values_id"), table_name="about_values")
    op.drop_table("about_values")
    op.drop_index(op.f("ix_about_strip_images_id"), table_name="about_strip_images")
    op.drop_table("about_strip_images")
