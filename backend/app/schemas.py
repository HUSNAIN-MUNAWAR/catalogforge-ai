from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class WorkspaceSwitchRequest(BaseModel):
    organization_id: str


class ProductUpdate(BaseModel):
    title: str | None = None
    sku: str | None = None
    category: str | None = None
    price: float | None = None
    inventory: int | None = None
    status: str | None = None
    attributes: dict[str, Any] | None = None


class BulkProductUpdate(BaseModel):
    ids: list[str] = Field(min_length=1)
    updates: ProductUpdate


class ReviewDecision(BaseModel):
    note: str | None = None
    reason: str | None = None


class ReviewAssignment(BaseModel):
    assignee: str


class ReviewerNote(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class DuplicateDecisionRequest(BaseModel):
    rationale: str = "Reviewed in synthetic demo workspace"
    canonical_product_id: str | None = None
    confirm_second_review: bool = False


class PublishRequest(BaseModel):
    destination_id: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    mode: Literal["Publish", "Dry run", "Validate only", "Changed records"] = "Publish"
    change_set_id: str | None = None


class RulePreviewRequest(BaseModel):
    rule_name: str
    field_name: str
    rule_type: str
    sample_value: str
    config: dict[str, Any] = Field(default_factory=dict)


class RuleCreateRequest(BaseModel):
    name: str
    field_name: str
    rule_type: str
    severity: str = "Warning"
    blocking: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    applies_to: dict[str, Any] = Field(default_factory=dict)


class MappingPreviewRequest(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class ChangeSetRequest(BaseModel):
    name: str
    product_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    risk_level: str = "Medium"


class ChangeApprovalRequest(BaseModel):
    decision: Literal["Approved", "Rejected"]
    note: str = ""


class ReportRequest(BaseModel):
    report_type: str
    name: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class ScheduledReportRequest(BaseModel):
    report_type: str
    cadence: str = "Weekly"
    delivery: str = "in_app"


class AlertActionRequest(BaseModel):
    action: Literal["acknowledge", "snooze", "resolve"]
    note: str = ""


class APIKeyRequest(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["documents.read"])
    expires_in_days: int = Field(default=90, ge=1, le=365)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str = "Executive Operations Brief"
    filters: dict[str, Any] = Field(default_factory=dict)


class ImportMappingRequest(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class RetentionRequestBody(BaseModel):
    request_type: str
    entity_type: str
    entity_id: str


class UploadResponse(BaseModel):
    job_id: str
    status: str
    message: str


class SourceEvidenceSchema(BaseModel):
    page: int
    bbox: dict[str, int]
    source_text: str
    confidence: float
    extraction_method: str


class ExtractedProductSchema(BaseModel):
    title: str
    sku: str = ""
    brand: str
    category: str
    price: float
    inventory: int = 0
    barcode: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    evidence: list[SourceEvidenceSchema] = Field(default_factory=list)


class PublicationResultSchema(BaseModel):
    publication_job_id: str
    status: str
    idempotency_key: str
    destination: str
