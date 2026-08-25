"""create persistent matches table

Revision ID: 20260825_0001
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260825_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matches",
        sa.Column("match_id", sa.String(length=80), nullable=False),
        sa.Column("player_steamid", sa.String(length=32), nullable=True),
        sa.Column("map_name", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("match_id"),
    )
    op.create_index("idx_matches_created_at", "matches", ["created_at"])
    op.create_index(
        "idx_matches_player_map",
        "matches",
        ["player_steamid", "map_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_matches_player_map", table_name="matches")
    op.drop_index("idx_matches_created_at", table_name="matches")
    op.drop_table("matches")
