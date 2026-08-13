"""Add a visitor-facing error column, separate from the operator's

Failures were stored once and shown to everyone, so a browser could receive
"SearchFailed: ... RapidAPI monthly quota is exhausted ... Set
FLIGHT_PROVIDER=mock". That names the vendor, leaks the exception type, and
instructs the visitor to reconfigure a server they do not run.

``error`` keeps the technical text for whoever operates this. ``user_error``
holds the translated, plain-language message, and that is the only one any
endpoint sends to a browser.

Revision ID: a91d4b2c8e05
Revises: 727e639f13e1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a91d4b2c8e05"
down_revision = "727e639f13e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: rows written before this migration have no translated message,
    # and the read path already falls back to a generic one.
    op.add_column("search_queries", sa.Column("user_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_queries", "user_error")
