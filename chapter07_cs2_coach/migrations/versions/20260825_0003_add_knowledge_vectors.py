"""add pgvector knowledge index

Revision ID: 20260825_0003
Revises: 20260825_0002
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "20260825_0003"
down_revision = "20260825_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_vectors",
        sa.Column("knowledge_id", sa.String(length=80), nullable=False),
        sa.Column("map_name", sa.String(length=80), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("knowledge_id"),
    )
    op.create_index("ix_knowledge_vectors_map_name", "knowledge_vectors", ["map_name"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_vectors_map_name", table_name="knowledge_vectors")
    op.drop_table("knowledge_vectors")
