"""Phase 2 enterprise product data governance upgrade.

Adds Phase 2 tables and backfills missing columns when upgrading a Phase 1 database.
The migration is intentionally inspection-aware because the original 0001 demo migration used
metadata.create_all; fresh databases already contain the current schema after 0001.

Revision ID: 0002_phase2_enterprise
Revises: 0001_initial
Create Date: 2026-07-07
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, inspect

from alembic import op
from app import models  # noqa: F401
from app.database import Base

revision = "0002_phase2_enterprise"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


# New scalar columns for existing Phase 1 tables. Foreign keys are enforced by application scope
# for compatibility with SQLite ALTER TABLE; fresh schemas retain model-level ForeignKey definitions.
ADDITIONS = {
    "organizations": [("slug", String(120)), ("data_retention_days", Integer()), ("status", String(50))],
    "users": [("active_organization_id", String(36)), ("is_active", Boolean()), ("last_login_at", DateTime())],
    "vendors": [("status", String(50)), ("notes", Text()), ("quality_score", Float()), ("source_freshness_days", Integer())],
    "vendor_templates": [("version", Integer()), ("status", String(50)), ("confidence_threshold", Float()), ("approved_by", String(255))],
    "upload_jobs": [("mode", String(80)), ("import_batch_id", String(36)), ("cancel_requested", Boolean()), ("source_quality_score", Float())],
    "source_documents": [("organization_id", String(36)), ("original_filename", String(500)), ("mime_type", String(150)), ("file_size", Integer()), ("source_type", String(80)), ("duplicate_of_id", String(36)), ("retention_state", String(50))],
    "source_pages": [("sheet_name", String(150)), ("row_number", Integer())],
    "ocr_blocks": [("method", String(100))],
    "product_candidates": [("parent_product_id", String(36)), ("vendor_sku", String(150)), ("product_type", String(255)), ("cost", Float()), ("currency", String(12)), ("completeness_score", Float()), ("quality_score", Float())],
    "extracted_fields": [("original_value", Text()), ("normalized_value", Text()), ("validation_status", String(50)), ("reviewer_override", Boolean()), ("reviewer_identity", String(255)), ("reviewed_at", DateTime()), ("transformation_history", Text()), ("destination_mapping", Text())],
    "product_images": [("alt_text", String(500))],
    "categories": [("version", Integer()), ("owner", String(255)), ("status", String(50))],
    "attribute_definitions": [("data_type", String(50)), ("unit_type", String(50)), ("validation_pattern", String(500)), ("status", String(50))],
    "validation_rules": [("severity", String(50)), ("blocking", Boolean()), ("version", Integer()), ("approval_state", String(50)), ("applies_to", Text())],
    "validation_results": [("blocking", Boolean()), ("remediation", Text())],
    "duplicate_groups": [("risk_level", String(50)), ("canonical_product_id", String(36)), ("second_review_required", Boolean())],
    "duplicate_decisions": [("approval_state", String(50))],
    "review_tasks": [("organization_id", String(36)), ("queue", String(100)), ("locked_by", String(255)), ("due_at", DateTime()), ("second_review", Boolean())],
    "reviewer_comments": [("mentions", Text())],
    "publication_destinations": [("status", String(50)), ("mapping_version", Integer()), ("required_fields", Text()), ("owner", String(255)), ("failure_count", Integer())],
    "publication_jobs": [("product_ids", Text()), ("mode", String(50)), ("dry_run", Boolean()), ("change_set_id", String(36))],
    "publication_attempts": [("response", Text())],
    "audit_events": [("request_id", String(100))],
    "api_keys": [("secret_hash", String(255)), ("scopes", Text()), ("expires_at", DateTime()), ("revoked_at", DateTime())],
    "webhook_deliveries": [("delivery_status", String(50)), ("retry_count", Integer()), ("payload_preview", Text())],
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, columns in ADDITIONS.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, type_ in columns:
            if column_name not in existing_columns:
                op.add_column(table_name, Column(column_name, type_, nullable=True))
    # All Phase 2-only tables are created from model metadata if missing.
    inspector = inspect(bind)
    for table_name, table in Base.metadata.tables.items():
        if table_name not in inspector.get_table_names():
            table.create(bind=bind)


def downgrade() -> None:
    # Conservative demo downgrade: Phase 2 records can carry governance evidence; avoid destructive automated drops.
    pass
