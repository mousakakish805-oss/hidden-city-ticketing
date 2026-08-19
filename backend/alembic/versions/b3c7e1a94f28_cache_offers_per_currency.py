"""Make currency part of the offer cache key

The cache stored one row per (provider, origin, destination, date, cabin,
adults) and recorded the currency as a property of that row rather than as
part of its identity. Searching a route in EUR after searching it in USD
therefore returned the USD offers with a EUR label, and the page rendered
euro totals beside dollar fares.

Adding a column to a unique constraint can only relax it, so no existing row
can conflict.

Revision ID: b3c7e1a94f28
Revises: a91d4b2c8e05
"""

from __future__ import annotations

from alembic import op

revision = "b3c7e1a94f28"
down_revision = "a91d4b2c8e05"
branch_labels = None
depends_on = None

COLUMNS = ["provider", "origin", "destination", "departure_date", "cabin", "adults"]
CONSTRAINT = "uq_offer_cache_key"


def upgrade() -> None:
    # batch_alter_table because SQLite cannot alter a constraint in place and
    # has to rebuild the table; on PostgreSQL this issues the ALTERs directly.
    with op.batch_alter_table("offer_cache") as batch:
        batch.drop_constraint(CONSTRAINT, type_="unique")
        batch.create_unique_constraint(CONSTRAINT, [*COLUMNS, "currency"])


def downgrade() -> None:
    # Rows that differ only by currency would collide under the old, narrower
    # constraint, so they are cleared first. This is a cache: the only cost of
    # emptying it is that the next search pays for its own probes.
    op.execute("DELETE FROM offer_cache")
    with op.batch_alter_table("offer_cache") as batch:
        batch.drop_constraint(CONSTRAINT, type_="unique")
        batch.create_unique_constraint(CONSTRAINT, COLUMNS)
