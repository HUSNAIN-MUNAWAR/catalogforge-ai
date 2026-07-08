"""Phase 3 launch hardening tables.

Adds launch-readiness checks, data contracts, and saved entity views. The migration is
metadata-driven and safe for fresh demo databases where model metadata may already exist.

Revision ID: 0003_phase3_launch_hardening
Revises: 0002_phase2_enterprise
Create Date: 2026-07-09
"""
from __future__ import annotations

from sqlalchemy import inspect

from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0003_phase3_launch_hardening"
down_revision = "0002_phase2_enterprise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for table_name in ["launch_readiness_checks", "data_contracts", "saved_entity_views"]:
        table = Base.metadata.tables[table_name]
        if table_name not in existing:
            table.create(bind=bind)


def downgrade() -> None:
    pass
