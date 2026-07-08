from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def uid() -> str:
    return str(uuid4())


class Timestamped(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class Organization(Timestamped):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, default="workspace")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    data_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    status: Mapped[str] = mapped_column(String(50), default="Active")


class User(Timestamped):
    __tablename__ = "users"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    active_organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(80), default="Viewer")
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkspaceMembership(Timestamped):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_user_org_membership"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(80), default="Viewer")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Role(Timestamped):
    __tablename__ = "roles"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)


class Vendor(Timestamped):
    __tablename__ = "vendors"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    contact_email: Mapped[str] = mapped_column(String(255))
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    template_name: Mapped[str] = mapped_column(String(200), default="Standard Retail v1")
    status: Mapped[str] = mapped_column(String(50), default="Active")
    notes: Mapped[str] = mapped_column(Text, default="")
    quality_score: Mapped[float] = mapped_column(Float, default=0.85)
    source_freshness_days: Mapped[int] = mapped_column(Integer, default=7)


class VendorTemplate(Timestamped):
    __tablename__ = "vendor_templates"
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="Approved")
    mappings: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.80)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VendorIntakeLink(Timestamped):
    __tablename__ = "vendor_intake_links"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    allowed_source_types: Mapped[dict] = mapped_column(JSON, default=dict)
    template_version: Mapped[str] = mapped_column(String(100), default="v1")
    status: Mapped[str] = mapped_column(String(50), default="Active")


class UploadJob(Timestamped):
    __tablename__ = "upload_jobs"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="Received")
    product_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    validation_failures: Mapped[int] = mapped_column(Integer, default=0)
    reviewer_name: Mapped[str] = mapped_column(String(200), default="Unassigned")
    destination: Mapped[str] = mapped_column(String(100), default="Shopify mock")
    mode: Mapped[str] = mapped_column(String(80), default="Extract and review")
    import_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    source_quality_score: Mapped[float] = mapped_column(Float, default=0.9)


class SourceDocument(Timestamped):
    __tablename__ = "source_documents"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    upload_job_id: Mapped[str] = mapped_column(ForeignKey("upload_jobs.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    mime_type: Mapped[str] = mapped_column(String(150), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(80), default="Unknown")
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    sha256: Mapped[str] = mapped_column(String(128), index=True)
    duplicate_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    retention_state: Mapped[str] = mapped_column(String(50), default="Active")
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class SourcePage(Timestamped):
    __tablename__ = "source_pages"
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_url: Mapped[str] = mapped_column(String(500))


class OCRBlock(Timestamped):
    __tablename__ = "ocr_blocks"
    source_page_id: Mapped[str] = mapped_column(ForeignKey("source_pages.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    method: Mapped[str] = mapped_column(String(100), default="deterministic_local_parser")


class ExtractionJob(Timestamped):
    __tablename__ = "extraction_jobs"
    upload_job_id: Mapped[str] = mapped_column(ForeignKey("upload_jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100), default="deterministic")
    status: Mapped[str] = mapped_column(String(50), default="completed")
    output_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class DurableJob(Timestamped):
    __tablename__ = "durable_jobs"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="Queued", index=True)
    related_entity_type: Mapped[str] = mapped_column(String(100), default="")
    related_entity_id: Mapped[str] = mapped_column(String(36), default="")
    source_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_identifier: Mapped[str] = mapped_column(String(100), default="inline-demo-worker")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_artifacts: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class JobEvent(Timestamped):
    __tablename__ = "job_events"
    durable_job_id: Mapped[str] = mapped_column(ForeignKey("durable_jobs.id"), index=True)
    state: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ProductCandidate(Timestamped):
    __tablename__ = "product_candidates"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    upload_job_id: Mapped[str | None] = mapped_column(ForeignKey("upload_jobs.id"), nullable=True, index=True)
    parent_product_id: Mapped[str | None] = mapped_column(ForeignKey("product_candidates.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    sku: Mapped[str] = mapped_column(String(150), index=True)
    vendor_sku: Mapped[str] = mapped_column(String(150), default="")
    brand: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(255))
    product_type: Mapped[str] = mapped_column(String(255), default="")
    price: Mapped[float] = mapped_column(Float)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(12), default="USD")
    inventory: Mapped[int] = mapped_column(Integer, default=0)
    barcode: Mapped[str] = mapped_column(String(50), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(50), default="Needs review")
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)


class ExtractedField(Timestamped):
    __tablename__ = "extracted_fields"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    original_value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(100), default="deterministic_parser")
    validation_status: Mapped[str] = mapped_column(String(50), default="Healthy")
    reviewer_override: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    transformation_history: Mapped[dict] = mapped_column(JSON, default=dict)
    destination_mapping: Mapped[dict] = mapped_column(JSON, default=dict)


class ProductImage(Timestamped):
    __tablename__ = "product_images"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    perceptual_hash: Mapped[str] = mapped_column(String(128))
    quality_score: Mapped[float] = mapped_column(Float, default=0.95)
    alt_text: Mapped[str] = mapped_column(String(500), default="")


class ProductRecord(Timestamped):
    __tablename__ = "product_records"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    publication_status: Mapped[str] = mapped_column(String(50), default="Draft")


class ProductVersion(Timestamped):
    __tablename__ = "product_versions"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(255))
    change_summary: Mapped[str] = mapped_column(Text)
    before_json: Mapped[dict] = mapped_column(JSON, default=dict)
    after_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ChannelReadiness(Timestamped):
    __tablename__ = "channel_readiness"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    destination_id: Mapped[str | None] = mapped_column(ForeignKey("publication_destinations.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="Blocked")
    blockers: Mapped[dict] = mapped_column(JSON, default=dict)
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)


class Category(Timestamped):
    __tablename__ = "categories"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    required_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner: Mapped[str] = mapped_column(String(255), default="Taxonomy Manager")
    status: Mapped[str] = mapped_column(String(50), default="Active")


class AttributeDefinition(Timestamped):
    __tablename__ = "attribute_definitions"
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    data_type: Mapped[str] = mapped_column(String(50), default="text")
    unit_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    allowed_values: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_pattern: Mapped[str | None] = mapped_column(String(500), nullable=True)
    channel_applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="Active")


class AttributeValue(Timestamped):
    __tablename__ = "attribute_values"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    attribute_definition_id: Mapped[str] = mapped_column(ForeignKey("attribute_definitions.id"), index=True)
    value: Mapped[str] = mapped_column(Text)


class ValidationRule(Timestamped):
    __tablename__ = "validation_rules"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    field_name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    severity: Mapped[str] = mapped_column(String(50), default="Warning")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approval_state: Mapped[str] = mapped_column(String(50), default="Approved")
    applies_to: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ValidationResult(Timestamped):
    __tablename__ = "validation_results"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    rule_name: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(50), default="open")
    blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    remediation: Mapped[str] = mapped_column(Text, default="")


class DuplicateGroup(Timestamped):
    __tablename__ = "duplicate_groups"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="Candidate")
    risk_level: Mapped[str] = mapped_column(String(50), default="Medium")
    canonical_product_id: Mapped[str | None] = mapped_column(ForeignKey("product_candidates.id"), nullable=True)
    second_review_required: Mapped[bool] = mapped_column(Boolean, default=False)


class DuplicateDecision(Timestamped):
    __tablename__ = "duplicate_decisions"
    duplicate_group_id: Mapped[str] = mapped_column(ForeignKey("duplicate_groups.id"), index=True)
    decision: Mapped[str] = mapped_column(String(50))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(255))
    approval_state: Mapped[str] = mapped_column(String(50), default="Completed")


class ReviewTask(Timestamped):
    __tablename__ = "review_tasks"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    assignee: Mapped[str] = mapped_column(String(255), default="Unassigned")
    priority: Mapped[str] = mapped_column(String(50), default="Normal")
    status: Mapped[str] = mapped_column(String(50), default="Open")
    reason: Mapped[str] = mapped_column(Text)
    queue: Mapped[str] = mapped_column(String(100), default="General review")
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    second_review: Mapped[bool] = mapped_column(Boolean, default=False)


class ReviewerComment(Timestamped):
    __tablename__ = "reviewer_comments"
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    author: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[dict] = mapped_column(JSON, default=dict)


class PublicationDestination(Timestamped):
    __tablename__ = "publication_destinations"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    destination_type: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="Demo connected")
    mapping_version: Mapped[int] = mapped_column(Integer, default=1)
    required_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[str] = mapped_column(String(255), default="Publishing Manager")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class PublicationJob(Timestamped):
    __tablename__ = "publication_jobs"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("publication_destinations.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="Queued")
    item_count: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    rollback_of: Mapped[str | None] = mapped_column(String(36), nullable=True)
    product_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(50), default="Publish")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    change_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PublicationAttempt(Timestamped):
    __tablename__ = "publication_attempts"
    publication_job_id: Mapped[str] = mapped_column(ForeignKey("publication_jobs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[dict] = mapped_column(JSON, default=dict)


class SyncLog(Timestamped):
    __tablename__ = "sync_logs"
    publication_job_id: Mapped[str] = mapped_column(ForeignKey("publication_jobs.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(50), default="info")


class ReconciliationIssue(Timestamped):
    __tablename__ = "reconciliation_issues"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    product_candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("publication_destinations.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="Open")
    issue_type: Mapped[str] = mapped_column(String(100))
    internal_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    destination_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution: Mapped[str] = mapped_column(Text, default="")


class ChangeSet(Timestamped):
    __tablename__ = "change_sets"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="Draft")
    created_by: Mapped[str] = mapped_column(String(255))
    risk_level: Mapped[str] = mapped_column(String(50), default="Medium")
    approval_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")


class ChangeSetItem(Timestamped):
    __tablename__ = "change_set_items"
    change_set_id: Mapped[str] = mapped_column(ForeignKey("change_sets.id"), index=True)
    product_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("product_candidates.id"), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    before_json: Mapped[dict] = mapped_column(JSON, default=dict)
    after_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_state: Mapped[str] = mapped_column(String(50), default="Healthy")


class ChangeApproval(Timestamped):
    __tablename__ = "change_approvals"
    change_set_id: Mapped[str] = mapped_column(ForeignKey("change_sets.id"), index=True)
    approver: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(50))
    note: Mapped[str] = mapped_column(Text, default="")


class Report(Timestamped):
    __tablename__ = "reports"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="Completed")
    generated_by: Mapped[str] = mapped_column(String(255))
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    data_freshness: Mapped[str] = mapped_column(String(255), default="Synthetic snapshot")
    export_id: Mapped[str] = mapped_column(String(100), unique=True)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ScheduledReport(Timestamped):
    __tablename__ = "scheduled_reports"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(120))
    cadence: Mapped[str] = mapped_column(String(80))
    delivery: Mapped[str] = mapped_column(String(80), default="in_app")
    status: Mapped[str] = mapped_column(String(50), default="Active")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Alert(Timestamped):
    __tablename__ = "alerts"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    category: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="Open")
    entity_type: Mapped[str] = mapped_column(String(100), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Watchlist(Timestamped):
    __tablename__ = "watchlists"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    filter_config: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[str] = mapped_column(String(255))


class AuditEvent(Timestamped):
    __tablename__ = "audit_events"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class APIKey(Timestamped):
    __tablename__ = "api_keys"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(40))
    secret_hash: Mapped[str] = mapped_column(String(255), default="")
    scopes: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WebhookDelivery(Timestamped):
    __tablename__ = "webhook_deliveries"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(150))
    endpoint: Mapped[str] = mapped_column(String(500))
    status_code: Mapped[int] = mapped_column(Integer)
    response_excerpt: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(50), default="Delivered")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_preview: Mapped[dict] = mapped_column(JSON, default=dict)


class LaunchReadinessCheck(Timestamped):
    __tablename__ = "launch_readiness_checks"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    gate_key: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="Not checked")
    severity: Mapped[str] = mapped_column(String(50), default="Info")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    remediation: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataContract(Timestamped):
    __tablename__ = "data_contracts"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    contract_type: Mapped[str] = mapped_column(String(100), default="destination")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="Active")
    owner_role: Mapped[str] = mapped_column(String(100), default="Publishing Manager")
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SavedEntityView(Timestamped):
    __tablename__ = "saved_entity_views"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    entity_type: Mapped[str] = mapped_column(String(100))
    owner: Mapped[str] = mapped_column(String(255))
    filter_config: Mapped[dict] = mapped_column(JSON, default=dict)
    column_config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)


class RetentionRequest(Timestamped):
    __tablename__ = "retention_requests"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(50), default="Needs review")
    requested_by: Mapped[str] = mapped_column(String(255))
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
