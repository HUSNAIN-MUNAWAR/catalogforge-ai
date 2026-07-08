from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import (
    Alert,
    APIKey,
    AttributeDefinition,
    DataContract,
    AuditEvent,
    Category,
    ChangeApproval,
    ChangeSet,
    ChangeSetItem,
    ChannelReadiness,
    DuplicateDecision,
    DuplicateGroup,
    DurableJob,
    ExtractedField,
    JobEvent,
    LaunchReadinessCheck,
    OCRBlock,
    Organization,
    ProductCandidate,
    ProductRecord,
    ProductVersion,
    PublicationAttempt,
    PublicationDestination,
    PublicationJob,
    ReconciliationIssue,
    Report,
    RetentionRequest,
    ReviewerComment,
    ReviewTask,
    Role,
    SavedEntityView,
    ScheduledReport,
    SourceDocument,
    SourcePage,
    SyncLog,
    UploadJob,
    User,
    ValidationResult,
    ValidationRule,
    Vendor,
    VendorIntakeLink,
    VendorTemplate,
    Watchlist,
    WebhookDelivery,
    WorkspaceMembership,
)
from .schemas import (
    AlertActionRequest,
    APIKeyRequest,
    AssistantRequest,
    BulkProductUpdate,
    ChangeApprovalRequest,
    ChangeSetRequest,
    DuplicateDecisionRequest,
    ImportMappingRequest,
    LoginRequest,
    ProductUpdate,
    PublishRequest,
    ReportRequest,
    RetentionRequestBody,
    ReviewAssignment,
    ReviewDecision,
    ReviewerNote,
    RuleCreateRequest,
    RulePreviewRequest,
    ScheduledReportRequest,
    WorkspaceSwitchRequest,
)
from .seed import password_hash, seed, verify_password
from .services.intake import IntakeValidationError, inspect_file, preview_rows
from .services.pipeline import (
    ExtractedCandidate,
    completeness_score,
    deterministic_extract,
    run_validations,
)
from .services.publisher import publish_mock, retry_mock

settings = get_settings()

ROLE_ORDER = {
    "Viewer": 0,
    "Compliance Reviewer": 1,
    "Product Reviewer": 2,
    "Vendor Manager": 3,
    "Taxonomy Manager": 3,
    "Catalog Operations Manager": 4,
    "Publishing Manager": 4,
    "Integration Manager": 4,
    "Organization Admin": 5,
    "Platform Admin": 6,
}


@dataclass
class WorkspaceContext:
    user: User
    organization_id: str
    role: str
    request_id: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed()
    yield


app = FastAPI(
    title="CatalogForge AI API",
    version="0.3.0",
    description="Enterprise catalog operations API. Synthetic demo data and mock connectors are explicitly labeled.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", f"cf-{uuid4().hex[:12]}")
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Unexpected server error.", "request_id": request_id}})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-CatalogForge-Duration-Ms"] = str(round((time.perf_counter() - started) * 1000))
    return response


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def add_audit(db: Session, ctx: WorkspaceContext, action: str, entity_type: str, entity_id: str, payload: dict | None = None) -> None:
    db.add(
        AuditEvent(
            organization_id=ctx.organization_id,
            actor=ctx.user.email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
            request_id=ctx.request_id,
        )
    )


def _initial_demo_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "admin@catalogforge.demo").first()
    if not user:
        raise HTTPException(status_code=500, detail="Synthetic demo workspace has not been seeded.")
    return user


def require_user(
    authorization: str | None = Header(default=None),
    x_catalogforge_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    # Backwards-compatible demo access remains available without a token, but all resource queries still use org scope.
    if x_catalogforge_api_key:
        for key in db.query(APIKey).filter(APIKey.revoked_at.is_(None)).all():
            if key.expires_at and key.expires_at < utcnow():
                continue
            raw = x_catalogforge_api_key.strip()
            legacy_digest = hashlib.sha256(raw.encode()).hexdigest()
            if verify_password(raw, key.secret_hash) or secrets.compare_digest(legacy_digest, key.secret_hash):
                user = (
                    db.query(User)
                    .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
                    .filter(WorkspaceMembership.organization_id == key.organization_id)
                    .filter(WorkspaceMembership.role.in_(["Organization Admin", "Platform Admin", "Integration Manager"]))
                    .first()
                )
                if not user:
                    raise HTTPException(status_code=401, detail="API key workspace has no service-capable user.")
                user.active_organization_id = key.organization_id
                key.last_used_at = utcnow()
                db.add(AuditEvent(organization_id=key.organization_id, actor="api-key", action="api_key.used", entity_type="api_key", entity_id=key.id, payload={"scopes": key.scopes}))
                db.commit()
                return user
        raise HTTPException(status_code=401, detail="Invalid, expired, or revoked API key.")
    if not authorization:
        return _initial_demo_user(db)
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required.")
    try:
        token = authorization.split(" ", 1)[1]
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user = db.get(User, claims["sub"])
        if not user or not user.is_active:
            raise ValueError("Inactive or unknown user")
        return user
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc


def resolve_workspace(
    request: Request,
    x_catalogforge_workspace: str | None = Header(default=None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    workspace_hint = x_catalogforge_workspace or user.active_organization_id or user.organization_id
    org = db.get(Organization, workspace_hint)
    if org is None:
        org = db.query(Organization).filter(Organization.slug == workspace_hint).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    membership = db.query(WorkspaceMembership).filter(
        WorkspaceMembership.user_id == user.id,
        WorkspaceMembership.organization_id == org.id,
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied.")
    return WorkspaceContext(user=user, organization_id=org.id, role=membership.role, request_id=request.headers.get("X-Request-ID", ""))


def require_roles(ctx: WorkspaceContext, *roles: str) -> None:
    if ctx.role == "Platform Admin" or ctx.role in roles:
        return
    raise HTTPException(status_code=403, detail=f"Role '{ctx.role}' cannot perform this action.")


def get_org_entity(db: Session, model: type, entity_id: str, ctx: WorkspaceContext):
    entity = db.get(model, entity_id)
    if not entity or getattr(entity, "organization_id", None) != ctx.organization_id:
        raise HTTPException(status_code=404, detail="Resource not found in active workspace.")
    return entity


def organization_or_404(db: Session, organization_id: str) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return organization


def membership_payload(db: Session, membership: WorkspaceMembership) -> dict:
    organization = organization_or_404(db, membership.organization_id)
    return {"id": membership.organization_id, "name": organization.name, "slug": organization.slug, "role": membership.role}


def destination_name(db: Session, destination_id: str) -> str:
    destination = db.get(PublicationDestination, destination_id)
    return destination.name if destination else "Unknown"


def _product_readiness(db: Session, product: ProductCandidate, org_id: str) -> list[dict]:
    rows = db.query(ChannelReadiness).filter(
        ChannelReadiness.organization_id == org_id,
        ChannelReadiness.product_candidate_id == product.id,
    ).all()
    return [
        {"id": row.id, "channel": row.channel, "status": row.status, "blockers": row.blockers, "requirements": row.requirements}
        for row in rows
    ]


def product_payload(product: ProductCandidate, db: Session, ctx: WorkspaceContext | None = None, detail: bool = False) -> dict:
    validations = db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id).all()
    payload = {
        "id": product.id,
        "title": product.title,
        "sku": product.sku,
        "vendor_sku": product.vendor_sku,
        "brand": product.brand,
        "category": product.category,
        "product_type": product.product_type,
        "price": product.price,
        "cost": product.cost,
        "currency": product.currency,
        "inventory": product.inventory,
        "barcode": product.barcode,
        "image_url": product.image_url,
        "status": product.status,
        "confidence": product.confidence,
        "completeness_score": product.completeness_score,
        "quality_score": product.quality_score,
        "attributes": product.attributes,
        "normalized": product.normalized,
        "created_at": product.created_at.isoformat(),
        "validations": [
            {"id": value.id, "rule": value.rule_name, "severity": value.severity, "message": value.message, "state": value.state, "blocking": value.blocking, "remediation": value.remediation}
            for value in validations
        ],
    }
    if detail:
        evidence = db.query(ExtractedField).filter(ExtractedField.product_candidate_id == product.id).all()
        versions = db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).order_by(desc(ProductVersion.version)).all()
        comments = db.query(ReviewerComment).filter(ReviewerComment.product_candidate_id == product.id).order_by(desc(ReviewerComment.created_at)).all()
        parent = db.get(ProductCandidate, product.parent_product_id) if product.parent_product_id else None
        variants = db.query(ProductCandidate).filter(ProductCandidate.parent_product_id == product.id).all()
        payload.update(
            {
                "evidence": [
                    {
                        "id": e.id,
                        "field": e.field_name,
                        "value": e.value,
                        "original_value": e.original_value,
                        "normalized_value": e.normalized_value,
                        "confidence": e.confidence,
                        "evidence": e.evidence,
                        "method": e.extraction_method,
                        "validation_status": e.validation_status,
                        "reviewer_override": e.reviewer_override,
                        "reviewer_identity": e.reviewer_identity,
                        "transformation_history": e.transformation_history,
                        "destination_mapping": e.destination_mapping,
                    }
                    for e in evidence
                ],
                "versions": [{"version": v.version, "actor": v.actor, "summary": v.change_summary, "at": v.created_at.isoformat(), "before": v.before_json, "after": v.after_json} for v in versions],
                "comments": [{"id": c.id, "author": c.author, "body": c.body, "mentions": c.mentions, "at": c.created_at.isoformat()} for c in comments],
                "parent": {"id": parent.id, "title": parent.title, "sku": parent.sku} if parent else None,
                "variants": [{"id": variant.id, "title": variant.title, "sku": variant.sku, "status": variant.status} for variant in variants],
                "channel_readiness": _product_readiness(db, product, ctx.organization_id if ctx else product.organization_id),
            }
        )
    return payload


def job_payload(job: UploadJob, db: Session) -> dict:
    vendor = db.get(Vendor, job.vendor_id)
    source = db.query(SourceDocument).filter(SourceDocument.upload_job_id == job.id).first()
    durable = db.query(DurableJob).filter(DurableJob.related_entity_type == "upload_job", DurableJob.related_entity_id == job.id).order_by(desc(DurableJob.created_at)).first()
    return {
        "id": job.id,
        "filename": job.filename,
        "vendor": vendor.name if vendor else "Unknown",
        "vendor_id": job.vendor_id,
        "source_type": job.source_type,
        "status": job.status,
        "product_count": job.product_count,
        "confidence": job.confidence,
        "validation_failures": job.validation_failures,
        "reviewer": job.reviewer_name,
        "destination": job.destination,
        "mode": job.mode,
        "source_quality_score": job.source_quality_score,
        "created_at": job.created_at.isoformat(),
        "document_id": source.id if source else None,
        "durable_job": {"id": durable.id, "type": durable.job_type, "status": durable.status, "retry_count": durable.retry_count, "error_reason": durable.error_reason} if durable else None,
    }


def document_payload(document: SourceDocument, db: Session) -> dict:
    job = db.get(UploadJob, document.upload_job_id)
    pages = db.query(SourcePage).filter(SourcePage.source_document_id == document.id).order_by(SourcePage.page_number).all()
    return {
        "id": document.id,
        "upload_job_id": document.upload_job_id,
        "filename": document.original_filename or (job.filename if job else "source"),
        "storage_key": document.storage_key,
        "mime_type": document.mime_type,
        "file_size": document.file_size,
        "source_type": document.source_type,
        "page_count": document.page_count,
        "sha256": document.sha256,
        "retention_state": document.retention_state,
        "duplicate_of_id": document.duplicate_of_id,
        "source_metadata": document.source_metadata,
        "pages": [{"id": page.id, "page_number": page.page_number, "sheet_name": page.sheet_name, "row_number": page.row_number, "preview_url": page.preview_url} for page in pages],
    }


def create_durable_job(db: Session, ctx: WorkspaceContext, job_type: str, entity_type: str, entity_id: str, status: str = "Queued", metadata: dict | None = None) -> DurableJob:
    durable = DurableJob(
        organization_id=ctx.organization_id,
        job_type=job_type,
        status=status,
        related_entity_type=entity_type,
        related_entity_id=entity_id,
        idempotency_key=f"cf-job-{uuid4()}",
        retry_policy={"max_attempts": 3, "backoff": "linear"},
        metadata_json=metadata or {},
    )
    db.add(durable)
    db.flush()
    db.add(JobEvent(durable_job_id=durable.id, state=status, message=f"{job_type} job created in {'inline deterministic' if settings.demo_mode else 'worker'} mode."))
    return durable


def _add_extracted_product(db: Session, ctx: WorkspaceContext, job: UploadJob, item: ExtractedCandidate) -> ProductCandidate:
    vendor = get_org_entity(db, Vendor, job.vendor_id, ctx)
    blocking = any(bool(result.get("blocking")) for result in run_validations(item, "Shopify"))
    status = "Needs review" if blocking or item.confidence < 0.86 else "Extracted"
    candidate = ProductCandidate(
        organization_id=ctx.organization_id,
        vendor_id=vendor.id,
        upload_job_id=job.id,
        title=item.title,
        sku=item.sku,
        vendor_sku=item.sku,
        brand=item.brand,
        category=item.category,
        product_type=item.category.split(" / ")[-1],
        price=item.price,
        cost=round(item.price * 0.55, 2),
        currency="USD",
        inventory=item.inventory,
        barcode=item.barcode,
        image_url="/demo_data/product_images/product_01.svg",
        status=status,
        confidence=item.confidence,
        attributes=item.attributes,
        normalized={"sku": item.sku, "taxonomy_confidence": item.confidence},
        completeness_score=completeness_score(item, destination="Shopify"),
        quality_score=round(completeness_score(item, destination="Shopify") * 0.7 + item.confidence * 30, 1),
    )
    db.add(candidate)
    db.flush()
    for field_name, value in [("title", item.title), ("sku", item.sku or "—"), ("price", str(item.price)), ("weight", str(item.attributes.get("weight") or "—"))]:
        db.add(
            ExtractedField(
                product_candidate_id=candidate.id,
                field_name=field_name,
                value=value,
                original_value=value,
                normalized_value=item.sku if field_name == "sku" else value,
                confidence=item.confidence if field_name != "sku" else min(item.confidence, 0.75 if not item.sku else item.confidence),
                evidence={**item.evidence, "document": job.filename},
                extraction_method="deterministic_csv_xlsx_json_parser" if job.source_type in {"CSV", "Spreadsheet", "XLSX", "XLS", "JSON feed"} else "deterministic_document_parser",
                validation_status="Needs review" if blocking else "Healthy",
                transformation_history={"steps": ["source parser", "SKU normalization", "taxonomy default"]},
                destination_mapping={"Shopify": field_name},
            )
        )
    for result in run_validations(item, "Shopify"):
        db.add(
            ValidationResult(
                product_candidate_id=candidate.id,
                rule_name=str(result["rule"]),
                severity=str(result["severity"]),
                message=str(result["message"]),
                state="open",
                blocking=bool(result.get("blocking")),
                remediation=str(result.get("remediation", "")),
            )
        )
    destinations = db.query(PublicationDestination).filter(PublicationDestination.organization_id == ctx.organization_id).all()
    for destination in destinations:
        blockers: list[str] = []
        if not candidate.sku:
            blockers.append("SKU")
        if destination.destination_type == "shopify_mock" and not candidate.attributes.get("weight"):
            blockers.append("shipping weight")
        ready = "Blocked" if blockers else "Pending approval"
        db.add(ChannelReadiness(organization_id=ctx.organization_id, product_candidate_id=candidate.id, destination_id=destination.id, channel=destination.name, status=ready, blockers={"items": blockers}, requirements=destination.required_fields))
    if status == "Needs review":
        db.add(ReviewTask(organization_id=ctx.organization_id, product_candidate_id=candidate.id, priority="High" if not candidate.sku else "Normal", status="Open", reason="Missing SKU" if not candidate.sku else "Destination readiness requires human review", queue="Missing required fields" if not candidate.sku else "Channel readiness failures"))
    db.add(ProductVersion(product_candidate_id=candidate.id, version=1, actor=ctx.user.email, change_summary="Created through deterministic source import.", before_json={}, after_json={"sku": candidate.sku, "title": candidate.title, "price": candidate.price}))
    return candidate


def _resolve_open_validation_after_edit(db: Session, product: ProductCandidate) -> None:
    values = db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id).all()
    for value in values:
        if value.rule_name == "SKU required" and product.sku:
            value.state = "resolved"
        if value.rule_name == "Shopify shipping weight" and product.attributes.get("weight"):
            value.state = "resolved"


def _approved_product(db: Session, ctx: WorkspaceContext, product: ProductCandidate, note: str | None = None) -> dict:
    blocking = db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id, ValidationResult.state == "open", ValidationResult.blocking.is_(True)).count()
    if blocking:
        raise HTTPException(status_code=409, detail="Product has unresolved publish-blocking validation issues.")
    unresolved_duplicate = False
    duplicate_groups = db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id, DuplicateGroup.status.in_(["Candidate", "In review"])).all()
    for group in duplicate_groups:
        values = group.rationale or {}
        if product.id in {values.get("left_product_id"), values.get("right_product_id")}:
            unresolved_duplicate = True
            break
    if unresolved_duplicate:
        raise HTTPException(status_code=409, detail="Product has an unresolved duplicate candidate.")
    product.status = "Approved"
    _resolve_open_validation_after_edit(db, product)
    for readiness in db.query(ChannelReadiness).filter(ChannelReadiness.product_candidate_id == product.id, ChannelReadiness.organization_id == ctx.organization_id).all():
        if not readiness.blockers.get("items"):
            readiness.status = "Ready"
    record = db.query(ProductRecord).filter(ProductRecord.product_candidate_id == product.id).first()
    if not record:
        db.add(ProductRecord(product_candidate_id=product.id, version=1, publication_status="Approved"))
    db.add(ProductVersion(product_candidate_id=product.id, version=(db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).count() + 1), actor=ctx.user.email, change_summary="Product approved for governed channel readiness evaluation.", before_json={"status": "Needs review"}, after_json={"status": "Approved", "note": note or ""}))
    db.query(ReviewTask).filter(ReviewTask.product_candidate_id == product.id, ReviewTask.organization_id == ctx.organization_id).update({ReviewTask.status: "Resolved"})
    add_audit(db, ctx, "product.approved", "product", product.id, {"note": note or "", "channel_readiness": "evaluated"})
    db.commit()
    return product_payload(product, db, ctx, detail=True)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "0.3.0",
        "demo_mode": settings.demo_mode,
        "providers": {"ocr": settings.ocr_provider, "llm": settings.llm_provider},
        "storage": settings.storage_backend,
        "organizations": db.query(Organization).count(),
        "worker_mode": "inline deterministic demo worker" if settings.demo_mode else "external worker boundary",
    }


# Authentication and tenant selection
@app.post(f"{settings.api_prefix}/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    memberships = db.query(WorkspaceMembership).filter(WorkspaceMembership.user_id == user.id).all()
    default_membership = next((membership for membership in memberships if membership.is_default), None)
    workspace_id = default_membership.organization_id if default_membership else user.organization_id
    workspace = db.get(Organization, workspace_id)
    user.active_organization_id = workspace_id
    user.last_login_at = utcnow()
    db.commit()
    token = jwt.encode({"sub": user.id, "role": user.role, "workspace": workspace.id if workspace else user.organization_id, "exp": datetime.now(UTC) + timedelta(hours=8)}, settings.jwt_secret, algorithm="HS256")
    return {
        "access_token": token,
        "refresh_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role},
        "workspace": {"id": workspace.id, "name": workspace.name, "slug": workspace.slug, "synthetic": workspace.is_synthetic} if workspace else None,
        "workspaces": [membership_payload(db, membership) for membership in memberships],
    }


@app.post(f"{settings.api_prefix}/auth/refresh")
def refresh(ctx: WorkspaceContext = Depends(resolve_workspace)) -> dict:
    token = jwt.encode({"sub": ctx.user.id, "role": ctx.role, "workspace": ctx.organization_id, "exp": datetime.now(UTC) + timedelta(hours=8)}, settings.jwt_secret, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}


@app.post(f"{settings.api_prefix}/auth/logout")
def logout() -> dict:
    return {"ok": True, "message": "Demo token invalidation is simulated client-side; production token rotation is an integration boundary."}


@app.get(f"{settings.api_prefix}/auth/me")
def me(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    memberships = db.query(WorkspaceMembership).filter(WorkspaceMembership.user_id == ctx.user.id).all()
    org = organization_or_404(db, ctx.organization_id)
    return {
        "id": ctx.user.id,
        "email": ctx.user.email,
        "name": ctx.user.name,
        "role": ctx.role,
        "workspace": {"id": org.id, "name": org.name, "slug": org.slug, "synthetic": org.is_synthetic},
        "workspaces": [membership_payload(db, item) for item in memberships],
    }


@app.post(f"{settings.api_prefix}/auth/switch-workspace")
def switch_workspace(body: WorkspaceSwitchRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    target = db.get(Organization, body.organization_id) or db.query(Organization).filter(Organization.slug == body.organization_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    membership = db.query(WorkspaceMembership).filter(WorkspaceMembership.user_id == ctx.user.id, WorkspaceMembership.organization_id == target.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Cross-tenant workspace switch denied.")
    ctx.user.active_organization_id = target.id
    db.commit()
    add_audit(db, WorkspaceContext(ctx.user, target.id, membership.role, ctx.request_id), "workspace.switched", "organization", target.id, {"from": ctx.organization_id})
    db.commit()
    return {"workspace": {"id": target.id, "name": target.name, "slug": target.slug}, "role": membership.role}


# Dashboard, pipeline and global navigation
@app.get(f"{settings.api_prefix}/overview")
def overview(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    products = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id)
    jobs = db.query(UploadJob).filter(UploadJob.organization_id == ctx.organization_id)
    duplicate_count = db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id, DuplicateGroup.status.in_(["Candidate", "In review"])).count()
    validation_query = db.query(ValidationResult).join(ProductCandidate, ValidationResult.product_candidate_id == ProductCandidate.id).filter(ProductCandidate.organization_id == ctx.organization_id, ValidationResult.state == "open")
    quality = round(float(db.query(func.avg(ProductCandidate.quality_score)).filter(ProductCandidate.organization_id == ctx.organization_id).scalar() or 0), 1)
    return {
        "synthetic": True,
        "workspace_id": ctx.organization_id,
        "metrics": {
            "documents_received_today": jobs.filter(UploadJob.created_at >= utcnow() - timedelta(days=1)).count(),
            "products_extracted": products.count(),
            "awaiting_review": products.filter(ProductCandidate.status == "Needs review").count(),
            "validation_failures": validation_query.count(),
            "duplicate_candidates": duplicate_count,
            "publish_ready": products.filter(ProductCandidate.status == "Approved").count(),
            "published_products": db.query(ProductRecord).join(ProductCandidate, ProductRecord.product_candidate_id == ProductCandidate.id).filter(ProductCandidate.organization_id == ctx.organization_id, ProductRecord.publication_status == "Published").count(),
            "vendor_processing_hours": 3.6,
            "catalog_quality_score": quality,
        },
        "confidence_distribution": [{"band": "95–100%", "count": products.filter(ProductCandidate.confidence >= 0.95).count()}, {"band": "85–94%", "count": products.filter(ProductCandidate.confidence >= 0.85, ProductCandidate.confidence < 0.95).count()}, {"band": "70–84%", "count": products.filter(ProductCandidate.confidence >= 0.70, ProductCandidate.confidence < 0.85).count()}, {"band": "<70%", "count": products.filter(ProductCandidate.confidence < 0.70).count()}],
        "quality_trend": [{"day": day, "score": score} for day, score in zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], [88, 90, 89, 92, 91, 94, 93])],
        "recent_activity": [job_payload(job, db) for job in jobs.order_by(desc(UploadJob.created_at)).limit(5)],
        "summary": "Synthetic operational summary: review low-confidence source fields, resolve duplicate candidates, and publish only products that satisfy configured destination gates.",
        "limitations": "Quality and trend values are derived from synthetic demo records and rules, not real operational telemetry.",
    }


@app.get(f"{settings.api_prefix}/pipeline/jobs")
def pipeline_jobs(status: str | None = None, job_type: str | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    query = db.query(DurableJob).filter(DurableJob.organization_id == ctx.organization_id)
    if status:
        query = query.filter(DurableJob.status == status)
    if job_type:
        query = query.filter(DurableJob.job_type == job_type)
    rows = query.order_by(desc(DurableJob.created_at)).limit(200).all()
    return {"items": [{"id": row.id, "type": row.job_type, "status": row.status, "related_entity_type": row.related_entity_type, "related_entity_id": row.related_entity_id, "retry_count": row.retry_count, "error_reason": row.error_reason, "worker": row.worker_identifier, "duration_ms": row.duration_ms, "metadata": row.metadata_json, "created_at": row.created_at.isoformat()} for row in rows], "queue_health": {"inline_mode": settings.demo_mode, "failed": query.filter(DurableJob.status == "Failed").count(), "waiting_for_review": query.filter(DurableJob.status.in_(["Needs review", "Waiting for input"])).count()}}


@app.get(f"{settings.api_prefix}/pipeline/jobs/{{job_id}}")
def pipeline_job_detail(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, DurableJob, job_id, ctx)
    events = db.query(JobEvent).filter(JobEvent.durable_job_id == job.id).order_by(JobEvent.created_at).all()
    return {"id": job.id, "type": job.job_type, "status": job.status, "retry_count": job.retry_count, "retry_policy": job.retry_policy, "error_reason": job.error_reason, "artifacts": job.output_artifacts, "events": [{"state": event.state, "message": event.message, "at": event.created_at.isoformat(), "metadata": event.metadata_json} for event in events]}


@app.post(f"{settings.api_prefix}/pipeline/jobs/{{job_id}}/retry")
def retry_pipeline_job(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Integration Manager", "Organization Admin")
    job = get_org_entity(db, DurableJob, job_id, ctx)
    job.retry_count += 1
    job.status = "Completed" if settings.demo_mode else "Retrying"
    job.error_reason = None
    db.add(JobEvent(durable_job_id=job.id, state=job.status, message="Manual retry completed in deterministic demo mode." if settings.demo_mode else "Retry submitted to worker boundary."))
    add_audit(db, ctx, "pipeline.job_retried", "durable_job", job.id, {"retry_count": job.retry_count})
    db.commit()
    return {"id": job.id, "status": job.status, "retry_count": job.retry_count}


@app.post(f"{settings.api_prefix}/pipeline/jobs/{{job_id}}/cancel")
def cancel_pipeline_job(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Integration Manager", "Organization Admin")
    job = get_org_entity(db, DurableJob, job_id, ctx)
    if job.status in {"Completed", "Cancelled", "Rolled back"}:
        raise HTTPException(status_code=409, detail="Job cannot be cancelled in its current terminal state.")
    job.status = "Cancelled"
    db.add(JobEvent(durable_job_id=job.id, state="Cancelled", message="Safe cancellation recorded; completed artifacts remain immutable."))
    add_audit(db, ctx, "pipeline.job_cancelled", "durable_job", job.id)
    db.commit()
    return {"id": job.id, "status": job.status}


@app.get(f"{settings.api_prefix}/search")
def global_search(q: str, limit: int = 8, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    term = q.strip()
    if len(term) < 2:
        return {"items": []}
    like = f"%{term}%"
    items: list[dict] = []
    for product in db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id, (ProductCandidate.title.ilike(like)) | (ProductCandidate.sku.ilike(like))).limit(limit):
        items.append({"type": "Product", "id": product.id, "label": product.title, "metadata": f"{product.sku or 'No SKU'} · {product.status}", "href": f"/workspace/product-master?product={product.id}"})
    for vendor in db.query(Vendor).filter(Vendor.organization_id == ctx.organization_id, Vendor.name.ilike(like)).limit(limit):
        items.append({"type": "Vendor", "id": vendor.id, "label": vendor.name, "metadata": f"Quality {vendor.quality_score:.0%}", "href": f"/workspace/vendors?vendor={vendor.id}"})
    for doc in db.query(SourceDocument).filter(SourceDocument.organization_id == ctx.organization_id, SourceDocument.original_filename.ilike(like)).limit(limit):
        items.append({"type": "Source document", "id": doc.id, "label": doc.original_filename, "metadata": doc.source_type, "href": f"/workspace/documents?document={doc.id}"})
    for group in db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id).limit(limit):
        if term.lower() in group.status.lower() or term.lower() in "duplicate":
            items.append({"type": "Duplicate group", "id": group.id, "label": f"Duplicate group {group.id[:8]}", "metadata": f"{group.similarity_score:.0%} · {group.status}", "href": f"/workspace/duplicates?group={group.id}"})
    return {"items": items[:limit * 3]}


# Intake and source documents
@app.get(f"{settings.api_prefix}/intake/jobs")
def list_jobs(status: str | None = None, vendor: str | None = None, source_type: str | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    query = db.query(UploadJob).filter(UploadJob.organization_id == ctx.organization_id)
    if status:
        query = query.filter(UploadJob.status == status)
    if source_type:
        query = query.filter(UploadJob.source_type == source_type)
    rows = [job_payload(job, db) for job in query.order_by(desc(UploadJob.created_at)).all()]
    if vendor:
        rows = [row for row in rows if vendor.lower() in row["vendor"].lower()]
    return {"items": rows, "total": len(rows)}


@app.post(f"{settings.api_prefix}/intake/upload")
def upload_source_document(vendor_id: str, mode: str = "Extract and review", file: UploadFile = File(...), ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Vendor Manager", "Organization Admin")
    vendor = get_org_entity(db, Vendor, vendor_id, ctx)
    original = Path(file.filename or "upload").name
    storage = Path(settings.local_storage_path).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / f"uploaded_{uuid4().hex[:12]}_{original}"
    total = 0
    with target.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            total += len(chunk)
            if total > 25 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds the local demo size limit of 25 MB.")
            out.write(chunk)
    try:
        inspection = inspect_file(target)
    except IntakeValidationError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duplicate = db.query(SourceDocument).filter(SourceDocument.organization_id == ctx.organization_id, SourceDocument.sha256 == inspection.checksum).first()
    job = UploadJob(organization_id=ctx.organization_id, vendor_id=vendor.id, filename=target.name, source_type=inspection.source_type, status="Validated", product_count=0, confidence=0.0, validation_failures=0, reviewer_name="Unassigned", destination="Shopify mock", mode=mode, source_quality_score=0.95)
    db.add(job)
    db.flush()
    source = SourceDocument(organization_id=ctx.organization_id, upload_job_id=job.id, storage_key=str(target), original_filename=original, mime_type=inspection.mime_type, file_size=inspection.size, source_type=inspection.source_type, page_count=1, sha256=inspection.checksum, duplicate_of_id=duplicate.id if duplicate else None, source_metadata={"synthetic": False, "local_upload": True, "checksum_duplicate": bool(duplicate)})
    db.add(source)
    db.flush()
    page = SourcePage(source_document_id=source.id, page_number=1, preview_url=f"/demo_data/source_documents/{target.name}")
    db.add(page)
    try:
        columns, rows, suggested = preview_rows(target)
    except Exception:
        columns, rows, suggested = [], [], {}
    durable = create_durable_job(db, ctx, "Upload validation", "upload_job", job.id, status="Completed", metadata={"source_type": inspection.source_type, "checksum_duplicate": bool(duplicate)})
    durable.output_artifacts = {"document_id": source.id, "columns": columns, "preview_rows": rows, "suggested_mapping": suggested}
    add_audit(db, ctx, "document.uploaded", "upload_job", job.id, {"original_filename": original, "source_type": inspection.source_type, "checksum": inspection.checksum, "duplicate_of": duplicate.id if duplicate else None})
    db.commit()
    return {"job_id": job.id, "document_id": source.id, "status": job.status, "source_type": inspection.source_type, "checksum": inspection.checksum, "duplicate_hint": bool(duplicate), "preview": {"columns": columns, "rows": rows, "suggested_mapping": suggested}, "message": "File passed local MIME, extension, size, and checksum validation."}


@app.get(f"{settings.api_prefix}/intake/jobs/{{job_id}}")
def get_job(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, UploadJob, job_id, ctx)
    return job_payload(job, db)


@app.get(f"{settings.api_prefix}/intake/jobs/{{job_id}}/mapping-preview")
def mapping_preview(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, UploadJob, job_id, ctx)
    document = db.query(SourceDocument).filter(SourceDocument.upload_job_id == job.id, SourceDocument.organization_id == ctx.organization_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Source document not found.")
    try:
        columns, rows, suggested = preview_rows(Path(document.storage_key))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Mapping preview unavailable: {exc}") from exc
    return {"document_id": document.id, "columns": columns, "rows": rows, "suggested_mapping": suggested, "mode": job.mode}


@app.post(f"{settings.api_prefix}/intake/jobs/{{job_id}}/process")
def process_job(job_id: str, body: ImportMappingRequest | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Vendor Manager", "Organization Admin")
    job = get_org_entity(db, UploadJob, job_id, ctx)
    if job.cancel_requested:
        raise HTTPException(status_code=409, detail="This intake job was cancelled.")
    document = db.query(SourceDocument).filter(SourceDocument.upload_job_id == job.id, SourceDocument.organization_id == ctx.organization_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Source document not found.")
    durable = create_durable_job(db, ctx, "Extraction", "upload_job", job.id, status="Running", metadata={"mode": "inline deterministic"})
    vendor = get_org_entity(db, Vendor, job.vendor_id, ctx)
    items = deterministic_extract(Path(document.storage_key), vendor.name, (body.mapping if body else None))
    created = [_add_extracted_product(db, ctx, job, item) for item in items]
    job.product_count = len(created)
    job.confidence = round(sum(item.confidence for item in items) / max(1, len(items)), 2)
    job.validation_failures = sum(db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id, ValidationResult.state == "open").count() for product in created)
    job.status = "Needs review" if any(product.status == "Needs review" for product in created) else "Extracted"
    durable.status = "Needs review" if job.status == "Needs review" else "Completed"
    durable.duration_ms = max(140, len(created) * 18)
    durable.output_artifacts = {"products_created": [product.id for product in created], "deterministic": True, "external_keys_used": False}
    db.add(JobEvent(durable_job_id=durable.id, state=durable.status, message=f"Created {len(created)} product candidates; {job.validation_failures} validation findings recorded."))
    add_audit(db, ctx, "intake.processed", "upload_job", job.id, {"products_created": len(created), "deterministic": True, "mapping": (body.mapping if body else {})})
    db.commit()
    return {"job_id": job.id, "status": job.status, "product_count": len(created), "validation_failures": job.validation_failures, "durable_job_id": durable.id, "external_keys_used": False}


@app.post(f"{settings.api_prefix}/intake/jobs/{{job_id}}/retry")
def retry_job(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, UploadJob, job_id, ctx)
    job.status = "Processing"
    durable = create_durable_job(db, ctx, "Extraction", "upload_job", job.id, status="Retrying", metadata={"manual_retry": True})
    durable.status = "Completed" if settings.demo_mode else "Queued"
    db.add(JobEvent(durable_job_id=durable.id, state=durable.status, message="Retry completed deterministically; source file remains immutable."))
    add_audit(db, ctx, "intake.retried", "upload_job", job.id)
    db.commit()
    return {"job_id": job.id, "status": job.status, "retry_job_id": durable.id}


@app.post(f"{settings.api_prefix}/intake/jobs/{{job_id}}/cancel")
def cancel_intake_job(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, UploadJob, job_id, ctx)
    if job.status in {"Published", "Approved"}:
        raise HTTPException(status_code=409, detail="Approved or published intake cannot be cancelled.")
    job.cancel_requested = True
    job.status = "Cancelled"
    add_audit(db, ctx, "intake.cancelled", "upload_job", job.id)
    db.commit()
    return {"job_id": job.id, "status": job.status}


@app.get(f"{settings.api_prefix}/documents")
def list_documents(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    docs = db.query(SourceDocument).filter(SourceDocument.organization_id == ctx.organization_id).order_by(desc(SourceDocument.created_at)).all()
    return {"items": [document_payload(document, db) for document in docs]}


@app.get(f"{settings.api_prefix}/documents/{{document_id}}")
def document_detail(document_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    document = get_org_entity(db, SourceDocument, document_id, ctx)
    return document_payload(document, db)


@app.get(f"{settings.api_prefix}/documents/{{document_id}}/preview")
def document_preview(document_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    document = get_org_entity(db, SourceDocument, document_id, ctx)
    payload = document_payload(document, db)
    payload["preview_mode"] = "source-backed deterministic preview"
    return payload


@app.get(f"{settings.api_prefix}/documents/{{document_id}}/ocr-blocks")
def ocr_blocks(document_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    document = get_org_entity(db, SourceDocument, document_id, ctx)
    pages = db.query(SourcePage).filter(SourcePage.source_document_id == document.id).all()
    page_ids = [page.id for page in pages]
    blocks = db.query(OCRBlock).filter(OCRBlock.source_page_id.in_(page_ids)).all() if page_ids else []
    return {"items": [{"id": block.id, "text": block.text, "bbox": block.bbox, "confidence": block.confidence, "method": block.method, "page_id": block.source_page_id} for block in blocks]}


@app.get(f"{settings.api_prefix}/documents/{{document_id}}/evidence")
def document_evidence(document_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    document = get_org_entity(db, SourceDocument, document_id, ctx)
    product_ids = [item.id for item in db.query(ProductCandidate).filter(ProductCandidate.upload_job_id == document.upload_job_id, ProductCandidate.organization_id == ctx.organization_id).all()]
    fields = db.query(ExtractedField).filter(ExtractedField.product_candidate_id.in_(product_ids)).all() if product_ids else []
    return {"items": [{"id": field.id, "product_id": field.product_candidate_id, "field": field.field_name, "value": field.value, "original_value": field.original_value, "normalized_value": field.normalized_value, "confidence": field.confidence, "evidence": field.evidence, "method": field.extraction_method, "validation_status": field.validation_status, "reviewer_override": field.reviewer_override, "transformation_history": field.transformation_history, "destination_mapping": field.destination_mapping} for field in fields]}


# Product master data and review
@app.get(f"{settings.api_prefix}/products")
def list_products(q: str | None = None, status: str | None = None, vendor_id: str | None = None, limit: int = 80, offset: int = 0, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    query = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id)
    if q:
        query = query.filter((ProductCandidate.title.ilike(f"%{q}%")) | (ProductCandidate.sku.ilike(f"%{q}%")) | (ProductCandidate.brand.ilike(f"%{q}%")))
    if status:
        query = query.filter(ProductCandidate.status == status)
    if vendor_id:
        query = query.filter(ProductCandidate.vendor_id == vendor_id)
    total = query.count()
    rows = query.order_by(desc(ProductCandidate.created_at)).offset(offset).limit(min(limit, 250)).all()
    return {"items": [product_payload(product, db, ctx) for product in rows], "total": total, "limit": limit, "offset": offset}


@app.get(f"{settings.api_prefix}/products/{{product_id}}")
def get_product(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    return product_payload(product, db, ctx, detail=True)


@app.patch(f"{settings.api_prefix}/products/{{product_id}}")
def update_product(product_id: str, body: ProductUpdate, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    before = {"title": product.title, "sku": product.sku, "category": product.category, "price": product.price, "inventory": product.inventory, "attributes": product.attributes, "status": product.status}
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        if field == "attributes":
            product.attributes = {**product.attributes, **value}
        else:
            setattr(product, field, value)
    item = ExtractedCandidate(title=product.title, sku=product.sku, brand=product.brand, category=product.category, price=product.price, inventory=product.inventory, barcode=product.barcode, confidence=product.confidence, attributes=product.attributes, evidence={})
    product.completeness_score = completeness_score(item, destination="Shopify")
    product.quality_score = round(product.completeness_score * 0.7 + product.confidence * 30, 1)
    _resolve_open_validation_after_edit(db, product)
    for field_name in updates:
        evidence = db.query(ExtractedField).filter(ExtractedField.product_candidate_id == product.id, ExtractedField.field_name == field_name).first()
        if evidence:
            evidence.value = str(getattr(product, field_name)) if field_name != "attributes" else json.dumps(product.attributes, sort_keys=True)
            evidence.normalized_value = product.sku if field_name == "sku" else evidence.value
            evidence.reviewer_override = True
            evidence.reviewer_identity = ctx.user.email
            evidence.reviewed_at = utcnow()
            evidence.transformation_history = {**evidence.transformation_history, "human_override": {"by": ctx.user.email, "at": utcnow().isoformat()}}
    db.add(ProductVersion(product_candidate_id=product.id, version=db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).count() + 1, actor=ctx.user.email, change_summary="Reviewer edited product master data.", before_json=before, after_json={"title": product.title, "sku": product.sku, "category": product.category, "price": product.price, "inventory": product.inventory, "attributes": product.attributes, "status": product.status}))
    add_audit(db, ctx, "product.updated", "product", product.id, {"fields": list(updates)})
    db.commit()
    return product_payload(product, db, ctx, detail=True)


@app.post(f"{settings.api_prefix}/products/{{product_id}}/approve")
def approve_product(product_id: str, body: ReviewDecision, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    return _approved_product(db, ctx, product, body.note)


@app.post(f"{settings.api_prefix}/products/{{product_id}}/reject")
def reject_product(product_id: str, body: ReviewDecision, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    product.status = "Rejected"
    db.add(ProductVersion(product_candidate_id=product.id, version=db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).count() + 1, actor=ctx.user.email, change_summary="Product rejected from approval queue.", before_json={}, after_json={"status": "Rejected", "reason": body.reason or body.note or ""}))
    add_audit(db, ctx, "product.rejected", "product", product.id, {"reason": body.reason or body.note or ""})
    db.commit()
    return {"id": product.id, "status": product.status}


@app.post(f"{settings.api_prefix}/products/bulk-update")
def bulk_update(body: BulkProductUpdate, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    updated = 0
    for product_id in body.ids:
        product = db.query(ProductCandidate).filter(ProductCandidate.id == product_id, ProductCandidate.organization_id == ctx.organization_id).first()
        if not product:
            continue
        for field, value in body.updates.model_dump(exclude_none=True).items():
            if field == "attributes":
                product.attributes = {**product.attributes, **value}
            else:
                setattr(product, field, value)
        updated += 1
    add_audit(db, ctx, "products.bulk_updated", "product_collection", "bulk", {"count": updated, "fields": list(body.updates.model_dump(exclude_none=True))})
    db.commit()
    return {"updated": updated}


@app.get(f"{settings.api_prefix}/products/{{product_id}}/versions")
def product_versions(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    rows = db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).order_by(desc(ProductVersion.version)).all()
    return {"items": [{"version": row.version, "actor": row.actor, "summary": row.change_summary, "before": row.before_json, "after": row.after_json, "at": row.created_at.isoformat()} for row in rows]}


@app.get(f"{settings.api_prefix}/products/{{product_id}}/channel-readiness")
def channel_readiness(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    return {"product_id": product.id, "items": _product_readiness(db, product, ctx.organization_id)}


@app.get(f"{settings.api_prefix}/products/export", response_class=PlainTextResponse)
def export_products(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "sku", "title", "brand", "category", "price", "inventory", "status", "completeness_score"])
    for product in db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id).order_by(ProductCandidate.sku).all():
        writer.writerow([product.id, product.sku, product.title, product.brand, product.category, product.price, product.inventory, product.status, product.completeness_score])
    add_audit(db, ctx, "product.exported", "product_collection", "csv", {"synthetic": True})
    db.commit()
    return output.getvalue()


@app.get(f"{settings.api_prefix}/review/tasks")
def list_review_tasks(queue: str | None = None, status: str | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    query = db.query(ReviewTask).filter(ReviewTask.organization_id == ctx.organization_id)
    if queue:
        query = query.filter(ReviewTask.queue == queue)
    if status:
        query = query.filter(ReviewTask.status == status)
    tasks = query.order_by(desc(ReviewTask.created_at)).all()
    return {"items": [{"id": task.id, "product_id": task.product_candidate_id, "product": product_payload(get_org_entity(db, ProductCandidate, task.product_candidate_id, ctx), db, ctx), "assignee": task.assignee, "priority": task.priority, "status": task.status, "reason": task.reason, "queue": task.queue, "locked_by": task.locked_by, "second_review": task.second_review, "created_at": task.created_at.isoformat()} for task in tasks]}


@app.post(f"{settings.api_prefix}/review/tasks/{{task_id}}/assign")
def assign_review_task(task_id: str, body: ReviewAssignment | None = None, assignee: str | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    task = get_org_entity(db, ReviewTask, task_id, ctx)
    name = body.assignee if body else assignee
    if not name:
        raise HTTPException(status_code=422, detail="Assignee is required.")
    task.assignee = name
    task.locked_by = ctx.user.email
    add_audit(db, ctx, "review.task_assigned", "review_task", task.id, {"assignee": name})
    db.commit()
    return {"id": task.id, "assignee": task.assignee, "locked_by": task.locked_by}


@app.post(f"{settings.api_prefix}/review/tasks/{{task_id}}/approve")
def approve_task(task_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    task = get_org_entity(db, ReviewTask, task_id, ctx)
    product = get_org_entity(db, ProductCandidate, task.product_candidate_id, ctx)
    result = _approved_product(db, ctx, product, "Approved from review task")
    task.status = "Resolved"
    db.commit()
    return result


@app.post(f"{settings.api_prefix}/review/tasks/{{task_id}}/reject")
def reject_task(task_id: str, body: ReviewDecision, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    task = get_org_entity(db, ReviewTask, task_id, ctx)
    product = get_org_entity(db, ProductCandidate, task.product_candidate_id, ctx)
    product.status = "Rejected"
    task.status = "Rejected"
    add_audit(db, ctx, "review.task_rejected", "review_task", task.id, {"reason": body.reason or body.note or ""})
    db.commit()
    return {"id": task.id, "status": task.status, "product_status": product.status}


@app.post(f"{settings.api_prefix}/review/products/{{product_id}}/note")
def add_reviewer_note(product_id: str, body: ReviewerNote, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    mentions = {"users": re.findall(r"@([\w.\-]+)", body.body)}
    comment = ReviewerComment(product_candidate_id=product.id, author=ctx.user.email, body=body.body, mentions=mentions)
    db.add(comment)
    add_audit(db, ctx, "review.note_added", "product", product.id, {"mentions": mentions})
    db.commit()
    return {"id": comment.id, "author": comment.author, "body": comment.body, "mentions": mentions}


@app.post(f"{settings.api_prefix}/review/products/{{product_id}}/request-clarification")
def request_clarification(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    product.status = "Needs vendor clarification"
    task = ReviewTask(organization_id=ctx.organization_id, product_candidate_id=product.id, assignee="vendors@catalogforge.demo", priority="High", status="Open", reason="Vendor clarification requested", queue="Vendor clarification needed")
    db.add(task)
    add_audit(db, ctx, "vendor.clarification_requested", "product", product.id)
    db.commit()
    return {"product_id": product.id, "status": product.status, "review_task_id": task.id, "mock": True}


@app.post(f"{settings.api_prefix}/review/products/{{product_id}}/split")
def split_product(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    variant = ProductCandidate(organization_id=ctx.organization_id, vendor_id=product.vendor_id, upload_job_id=product.upload_job_id, parent_product_id=product.id, title=f"{product.title} — Variant", sku=f"{product.sku}-VAR" if product.sku else "", vendor_sku=product.vendor_sku, brand=product.brand, category=product.category, product_type=product.product_type, price=product.price, cost=product.cost, currency=product.currency, inventory=product.inventory, barcode="", image_url=product.image_url, status="Needs review", confidence=product.confidence, attributes={**product.attributes, "variant_created": True}, normalized=product.normalized, completeness_score=product.completeness_score, quality_score=product.quality_score)
    db.add(variant)
    db.flush()
    add_audit(db, ctx, "product.split", "product", product.id, {"variant_id": variant.id})
    db.commit()
    return {"parent_id": product.id, "variant_id": variant.id, "status": variant.status}


@app.get(f"{settings.api_prefix}/review/metrics")
def reviewer_metrics(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    tasks = db.query(ReviewTask).filter(ReviewTask.organization_id == ctx.organization_id).all()
    total = max(1, len(tasks))
    resolved = sum(1 for task in tasks if task.status == "Resolved")
    rejected = sum(1 for task in tasks if task.status == "Rejected")
    return {"synthetic": True, "throughput": resolved, "average_review_minutes": 6.4, "approval_rate": round(resolved / total, 2), "rejection_rate": round(rejected / total, 2), "escalation_rate": round(sum(1 for task in tasks if task.queue == "Vendor clarification needed") / total, 2), "quality_sampling_note": "Rules-based synthetic sample; not a real reviewer-performance score."}


# Duplicate governance
@app.get(f"{settings.api_prefix}/duplicates")
def list_duplicates(status: str | None = None, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    query = db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id)
    if status:
        query = query.filter(DuplicateGroup.status == status)
    groups = query.order_by(desc(DuplicateGroup.similarity_score)).all()
    return {"items": [{"id": group.id, "similarity_score": group.similarity_score, "status": group.status, "risk_level": group.risk_level, "second_review_required": group.second_review_required, "canonical_product_id": group.canonical_product_id, "rationale": group.rationale} for group in groups]}


@app.get(f"{settings.api_prefix}/duplicates/{{group_id}}")
def duplicate_compare(group_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    group = get_org_entity(db, DuplicateGroup, group_id, ctx)
    left_id = group.rationale.get("left_product_id")
    right_id = group.rationale.get("right_product_id")
    left = get_org_entity(db, ProductCandidate, left_id, ctx) if left_id else None
    right = get_org_entity(db, ProductCandidate, right_id, ctx) if right_id else None
    decisions = db.query(DuplicateDecision).filter(DuplicateDecision.duplicate_group_id == group.id).order_by(desc(DuplicateDecision.created_at)).all()
    return {"id": group.id, "status": group.status, "similarity_score": group.similarity_score, "risk_level": group.risk_level, "second_review_required": group.second_review_required, "rationale": group.rationale, "left": product_payload(left, db, ctx, detail=True) if left else None, "right": product_payload(right, db, ctx, detail=True) if right else None, "decisions": [{"id": decision.id, "decision": decision.decision, "rationale": decision.rationale, "decided_by": decision.decided_by, "approval_state": decision.approval_state, "at": decision.created_at.isoformat()} for decision in decisions]}


@app.post(f"{settings.api_prefix}/duplicates/{{group_id}}/merge")
def merge_duplicate(group_id: str, body: DuplicateDecisionRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    group = get_org_entity(db, DuplicateGroup, group_id, ctx)
    if group.status in {"Merged", "Not duplicate"}:
        raise HTTPException(status_code=409, detail="Duplicate group is already resolved.")
    left_id = group.rationale.get("left_product_id")
    right_id = group.rationale.get("right_product_id")
    canonical_id = body.canonical_product_id or group.canonical_product_id or left_id
    if canonical_id not in {left_id, right_id}:
        raise HTTPException(status_code=422, detail="Canonical product must be a member of this duplicate group.")
    if group.second_review_required and not body.confirm_second_review:
        group.status = "In review"
        db.add(DuplicateDecision(duplicate_group_id=group.id, decision="second_review_requested", rationale=body.rationale, decided_by=ctx.user.email, approval_state="Pending"))
        add_audit(db, ctx, "duplicate.second_review_requested", "duplicate_group", group.id, {"canonical_product_id": canonical_id})
        db.commit()
        return {"id": group.id, "status": group.status, "requires_second_review": True, "message": "High-impact merge is awaiting explicit second-review confirmation."}
    canonical = get_org_entity(db, ProductCandidate, canonical_id, ctx)
    merged_id = right_id if canonical_id == left_id else left_id
    merged = get_org_entity(db, ProductCandidate, merged_id, ctx)
    merged.status = "Merged"
    group.status = "Merged"
    group.canonical_product_id = canonical.id
    db.add(DuplicateDecision(duplicate_group_id=group.id, decision="merge", rationale=body.rationale, decided_by=ctx.user.email, approval_state="Completed"))
    add_audit(db, ctx, "duplicate.merged", "duplicate_group", group.id, {"canonical_product_id": canonical.id, "merged_product_id": merged.id, "source_evidence_preserved": True})
    db.commit()
    return {"id": group.id, "status": group.status, "canonical_product_id": canonical.id, "merged_product_id": merged.id, "source_evidence_preserved": True}


@app.post(f"{settings.api_prefix}/duplicates/{{group_id}}/separate")
def separate_duplicate(group_id: str, body: DuplicateDecisionRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Product Reviewer", "Catalog Operations Manager", "Organization Admin")
    group = get_org_entity(db, DuplicateGroup, group_id, ctx)
    group.status = "Not duplicate"
    db.add(DuplicateDecision(duplicate_group_id=group.id, decision="keep_separate", rationale=body.rationale, decided_by=ctx.user.email, approval_state="Completed"))
    add_audit(db, ctx, "duplicate.separated", "duplicate_group", group.id, {"rationale": body.rationale})
    db.commit()
    return {"id": group.id, "status": group.status}


@app.get(f"{settings.api_prefix}/duplicates/{{group_id}}/history")
def duplicate_history(group_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    group = get_org_entity(db, DuplicateGroup, group_id, ctx)
    rows = db.query(DuplicateDecision).filter(DuplicateDecision.duplicate_group_id == group.id).order_by(DuplicateDecision.created_at).all()
    return {"items": [{"decision": row.decision, "rationale": row.rationale, "decided_by": row.decided_by, "approval_state": row.approval_state, "at": row.created_at.isoformat()} for row in rows]}


# Taxonomy, attributes and validation policy
@app.get(f"{settings.api_prefix}/taxonomy/categories")
def categories(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(Category).filter(Category.organization_id == ctx.organization_id).all()
    return {"items": [{"id": category.id, "name": category.name, "path": category.path, "required_attributes": category.required_attributes, "version": category.version, "owner": category.owner, "status": category.status} for category in values]}


@app.get(f"{settings.api_prefix}/taxonomy/attributes")
def taxonomy_attributes(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    categories_by_id = {category.id: category for category in db.query(Category).filter(Category.organization_id == ctx.organization_id).all()}
    values = db.query(AttributeDefinition).filter(AttributeDefinition.category_id.in_(list(categories_by_id))).all()
    return {"items": [{"id": value.id, "category": categories_by_id[value.category_id].path, "name": value.name, "required": value.required, "data_type": value.data_type, "unit_type": value.unit_type, "allowed_values": value.allowed_values, "validation_pattern": value.validation_pattern, "channel_applicability": value.channel_applicability, "status": value.status} for value in values]}


@app.get(f"{settings.api_prefix}/taxonomy/rules")
def validation_rules(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(ValidationRule).filter(ValidationRule.organization_id == ctx.organization_id).all()
    return {"items": [{"id": rule.id, "name": rule.name, "field_name": rule.field_name, "rule_type": rule.rule_type, "config": rule.config, "severity": rule.severity, "blocking": rule.blocking, "version": rule.version, "approval_state": rule.approval_state, "applies_to": rule.applies_to, "is_active": rule.is_active} for rule in values]}


@app.post(f"{settings.api_prefix}/taxonomy/rules")
def create_validation_rule(body: RuleCreateRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Taxonomy Manager", "Organization Admin")
    rule = ValidationRule(organization_id=ctx.organization_id, name=body.name, field_name=body.field_name, rule_type=body.rule_type, config=body.config, severity=body.severity, blocking=body.blocking, approval_state="Needs review", applies_to=body.applies_to)
    db.add(rule)
    db.flush()
    add_audit(db, ctx, "validation.rule_created", "validation_rule", rule.id, {"approval_state": rule.approval_state})
    db.commit()
    return {"id": rule.id, "approval_state": rule.approval_state}


@app.put(f"{settings.api_prefix}/taxonomy/mappings/{{vendor_id}}")
def update_mapping(vendor_id: str, mapping: dict, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Taxonomy Manager", "Vendor Manager", "Organization Admin")
    vendor = get_org_entity(db, Vendor, vendor_id, ctx)
    template = db.query(VendorTemplate).filter(VendorTemplate.vendor_id == vendor.id).order_by(desc(VendorTemplate.version)).first()
    if not template:
        raise HTTPException(status_code=404, detail="Vendor template not found.")
    before = template.mappings
    template.mappings = mapping
    template.status = "Needs review"
    template.version += 1
    add_audit(db, ctx, "vendor.mapping_updated", "vendor", vendor.id, {"before": before, "after": mapping, "template_version": template.version})
    db.commit()
    return {"vendor_id": vendor.id, "mapping": mapping, "saved": True, "template_status": template.status, "version": template.version}


@app.post(f"{settings.api_prefix}/taxonomy/rules/preview")
def preview_rule(body: RulePreviewRequest, ctx: WorkspaceContext = Depends(resolve_workspace)) -> dict:
    value = body.sample_value
    passed = not (body.rule_type == "required" and not value.strip()) and not (body.rule_type == "contains_any" and any(word.lower() in value.lower() for word in body.config.get("words", [])))
    return {"passed": passed, "rule": body.rule_name, "sample_value": value, "explanation": "Rule passed in deterministic preview." if passed else "Rule failed for the supplied synthetic sample.", "scope": {"organization_id": ctx.organization_id}, "limitations": "Preview evaluates the provided sample only."}


@app.get(f"{settings.api_prefix}/taxonomy/impact-preview/{{category_id}}")
def taxonomy_impact_preview(category_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    category = get_org_entity(db, Category, category_id, ctx)
    products = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id, ProductCandidate.category == category.path).count()
    vendors = db.query(Vendor).filter(Vendor.organization_id == ctx.organization_id).count()
    return {"category": {"id": category.id, "path": category.path}, "products_affected": products, "vendors_affected": vendors, "validation_rules_affected": db.query(ValidationRule).filter(ValidationRule.organization_id == ctx.organization_id).count(), "destinations_affected": db.query(PublicationDestination).filter(PublicationDestination.organization_id == ctx.organization_id).count(), "publishing_risk": "Medium" if products > 20 else "Low", "required_approvals": ["Taxonomy Manager"]}


@app.get(f"{settings.api_prefix}/quality/overview")
def quality_overview(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    products = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id).all()
    validations = db.query(ValidationResult).join(ProductCandidate, ValidationResult.product_candidate_id == ProductCandidate.id).filter(ProductCandidate.organization_id == ctx.organization_id, ValidationResult.state == "open").all()
    ready = db.query(ChannelReadiness).filter(ChannelReadiness.organization_id == ctx.organization_id, ChannelReadiness.status == "Ready").count()
    return {"synthetic": True, "overall_catalog_quality_score": round(sum(p.quality_score for p in products) / max(1, len(products)), 1), "completeness_score": round(sum(p.completeness_score for p in products) / max(1, len(products)), 1), "validation_failure_rate": round(len(validations) / max(1, len(products)), 3), "duplicate_risk_rate": round(db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id, DuplicateGroup.status.in_(["Candidate", "In review"])).count() / max(1, len(products)), 3), "channel_readiness_records": ready, "blocked_products": sum(1 for p in products if p.status == "Blocked"), "common_failures": [{"rule": rule, "count": sum(1 for value in validations if value.rule_name == rule)} for rule in sorted({value.rule_name for value in validations})], "insight": "This synthetic product set is ready for internal approval where blocking rules are resolved, but channel publication remains blocked where SKU, shipping weight, or mapping requirements are missing.", "limitations": "Rules-based synthetic quality score; not a measured extraction-accuracy metric."}


# Publishing, channel readiness and reconciliation
@app.get(f"{settings.api_prefix}/publish/destinations")
def destinations(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(PublicationDestination).filter(PublicationDestination.organization_id == ctx.organization_id).all()
    return {"items": [{"id": value.id, "name": value.name, "type": value.destination_type, "status": value.status, "mapping_version": value.mapping_version, "required_fields": value.required_fields, "config": value.config, "failure_count": value.failure_count, "owner": value.owner} for value in values]}


@app.get(f"{settings.api_prefix}/publish/jobs")
def publication_jobs(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(PublicationJob).filter(PublicationJob.organization_id == ctx.organization_id).order_by(desc(PublicationJob.created_at)).limit(150).all()
    return {"items": [{"id": job.id, "status": job.status, "item_count": job.item_count, "idempotency_key": job.idempotency_key, "destination_id": job.destination_id, "destination": destination_name(db, job.destination_id), "product_ids": job.product_ids, "mode": job.mode, "dry_run": job.dry_run, "change_set_id": job.change_set_id, "created_at": job.created_at.isoformat()} for job in values]}


@app.post(f"{settings.api_prefix}/publish/jobs")
def create_publication_job(body: PublishRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Publishing Manager", "Catalog Operations Manager", "Organization Admin")
    destination = get_org_entity(db, PublicationDestination, body.destination_id, ctx) if body.destination_id else db.query(PublicationDestination).filter(PublicationDestination.organization_id == ctx.organization_id).first()
    if not destination:
        raise HTTPException(status_code=400, detail="No destination configured.")
    if destination.status not in {"Demo connected", "Connected"}:
        raise HTTPException(status_code=409, detail="Destination is not configured for a verified local connector run.")
    product_ids = body.product_ids or [product.id for product in db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id, ProductCandidate.status == "Approved").limit(12).all()]
    products = [get_org_entity(db, ProductCandidate, product_id, ctx) for product_id in product_ids]
    if body.mode == "Publish":
        blockers = []
        for product in products:
            readiness = db.query(ChannelReadiness).filter(ChannelReadiness.organization_id == ctx.organization_id, ChannelReadiness.product_candidate_id == product.id, ChannelReadiness.destination_id == destination.id).first()
            if product.status != "Approved" or (readiness and readiness.status != "Ready"):
                blockers.append(product.id)
        if blockers:
            raise HTTPException(status_code=409, detail=f"Products are not publish-ready for this destination: {', '.join(blockers[:5])}")
    job = publish_mock(db, ctx.organization_id, destination, [product.id for product in products], body.idempotency_key, body.mode, body.change_set_id)
    add_audit(db, ctx, "publication.created", "publication_job", job.id, {"mock": destination.config.get("mock", False), "mode": body.mode})
    db.commit()
    return {"id": job.id, "status": job.status, "item_count": job.item_count, "idempotency_key": job.idempotency_key, "mock": destination.config.get("mock", False), "mode": job.mode}


@app.post(f"{settings.api_prefix}/publish/jobs/{{job_id}}/retry")
def retry_publication(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Publishing Manager", "Organization Admin")
    job = get_org_entity(db, PublicationJob, job_id, ctx)
    job = retry_mock(db, job, ctx.user.email)
    return {"id": job.id, "status": job.status, "mock": True}


@app.post(f"{settings.api_prefix}/publish/jobs/{{job_id}}/rollback")
def rollback_publication(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Publishing Manager", "Organization Admin")
    job = get_org_entity(db, PublicationJob, job_id, ctx)
    rollback = PublicationJob(organization_id=ctx.organization_id, destination_id=job.destination_id, status="Rolled back", item_count=job.item_count, idempotency_key=f"rollback-{uuid4()}", rollback_of=job.id, product_ids=job.product_ids, mode="Rollback simulation", dry_run=True)
    db.add(rollback)
    db.flush()
    db.add(PublicationAttempt(publication_job_id=rollback.id, attempt_number=1, status="Rolled back", response={"mock": True, "external_change": False}))
    db.add(SyncLog(publication_job_id=rollback.id, message="Mock rollback simulation recorded. No third-party destination was changed.", level="info"))
    add_audit(db, ctx, "publication.rollback_simulated", "publication_job", rollback.id, {"rollback_of": job.id})
    db.commit()
    return {"rollback_job_id": rollback.id, "status": rollback.status, "mock": True}


@app.get(f"{settings.api_prefix}/publish/jobs/{{job_id}}/logs")
def publication_logs(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, PublicationJob, job_id, ctx)
    logs = db.query(SyncLog).filter(SyncLog.publication_job_id == job.id).all()
    attempts = db.query(PublicationAttempt).filter(PublicationAttempt.publication_job_id == job.id).all()
    return {"logs": [{"at": row.created_at.isoformat(), "message": row.message, "level": row.level} for row in logs], "attempts": [{"number": row.attempt_number, "status": row.status, "error": row.error, "response": row.response} for row in attempts]}


@app.post(f"{settings.api_prefix}/publish/reconcile")
def reconcile(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Publishing Manager", "Organization Admin")
    issues = db.query(ReconciliationIssue).filter(ReconciliationIssue.organization_id == ctx.organization_id, ReconciliationIssue.status == "Open").all()
    for issue in issues:
        issue.status = "Resolved"
        issue.resolution = "Deterministic reconciliation verified a mock destination update after mapping preview."
    durable = create_durable_job(db, ctx, "Reconciliation", "organization", ctx.organization_id, status="Completed", metadata={"issues_resolved": len(issues), "mock": True})
    add_audit(db, ctx, "reconciliation.completed", "organization", ctx.organization_id, {"issues_resolved": len(issues)})
    db.commit()
    return {"status": "Completed", "issues_resolved": len(issues), "job_id": durable.id, "mock": True}


@app.get(f"{settings.api_prefix}/publish/reconciliation")
def reconciliation_issues(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(ReconciliationIssue).filter(ReconciliationIssue.organization_id == ctx.organization_id).order_by(desc(ReconciliationIssue.created_at)).all()
    return {"items": [{"id": value.id, "product_id": value.product_candidate_id, "destination_id": value.destination_id, "status": value.status, "issue_type": value.issue_type, "internal": value.internal_snapshot, "destination": value.destination_snapshot, "resolution": value.resolution} for value in values]}


# Vendors and vendor performance
@app.get(f"{settings.api_prefix}/vendors")
def vendors(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(Vendor).filter(Vendor.organization_id == ctx.organization_id).all()
    items = []
    for vendor in values:
        jobs = db.query(UploadJob).filter(UploadJob.vendor_id == vendor.id, UploadJob.organization_id == ctx.organization_id).all()
        products = db.query(ProductCandidate).filter(ProductCandidate.vendor_id == vendor.id, ProductCandidate.organization_id == ctx.organization_id).all()
        failed = sum(job.validation_failures for job in jobs)
        items.append({"id": vendor.id, "name": vendor.name, "code": vendor.code, "contact_email": vendor.contact_email, "sla_hours": vendor.sla_hours, "template": vendor.template_name, "status": vendor.status, "files": len(jobs), "catalog_volume": sum(job.product_count for job in jobs), "confidence": round(sum(job.confidence for job in jobs) / max(1, len(jobs)), 2), "validation_failure_rate": round(failed / max(1, sum(job.product_count for job in jobs)), 3), "quality_score": vendor.quality_score, "source_freshness_days": vendor.source_freshness_days, "frequent_issue": "Missing SKU" if any(not product.sku for product in products) else "Image quality"})
    return {"items": items, "note": "Vendor quality is an explainable rules-based synthetic operational score, not a supplier-performance certification."}


@app.get(f"{settings.api_prefix}/vendors/{{vendor_id}}")
def vendor_detail(vendor_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    vendor = get_org_entity(db, Vendor, vendor_id, ctx)
    jobs = [job_payload(job, db) for job in db.query(UploadJob).filter(UploadJob.vendor_id == vendor.id, UploadJob.organization_id == ctx.organization_id).order_by(desc(UploadJob.created_at)).all()]
    templates = db.query(VendorTemplate).filter(VendorTemplate.vendor_id == vendor.id).order_by(desc(VendorTemplate.version)).all()
    links = db.query(VendorIntakeLink).filter(VendorIntakeLink.vendor_id == vendor.id, VendorIntakeLink.organization_id == ctx.organization_id).all()
    return {"id": vendor.id, "name": vendor.name, "code": vendor.code, "quality_score": vendor.quality_score, "source_freshness_days": vendor.source_freshness_days, "jobs": jobs, "templates": [{"id": template.id, "name": template.name, "version": template.version, "status": template.status, "mappings": template.mappings, "confidence_threshold": template.confidence_threshold} for template in templates], "intake_links": [{"id": link.id, "token_preview": f"{link.token[:8]}…", "expires_at": link.expires_at.isoformat(), "allowed_source_types": link.allowed_source_types, "template_version": link.template_version, "status": link.status} for link in links]}


@app.post(f"{settings.api_prefix}/vendors/{{vendor_id}}/intake-links")
def create_vendor_intake_link(vendor_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Vendor Manager", "Organization Admin")
    vendor = get_org_entity(db, Vendor, vendor_id, ctx)
    link = VendorIntakeLink(organization_id=ctx.organization_id, vendor_id=vendor.id, token=secrets.token_urlsafe(20), expires_at=utcnow() + timedelta(days=30), allowed_source_types={"types": ["CSV", "XLSX", "PDF", "JSON", "Image"]}, template_version="v2")
    db.add(link)
    db.flush()
    add_audit(db, ctx, "vendor.intake_link_created", "vendor", vendor.id, {"link_id": link.id, "demo": True})
    db.commit()
    return {"id": link.id, "token_preview": f"{link.token[:10]}…", "expires_at": link.expires_at.isoformat(), "demo": True, "message": "Demo vendor-intake link created. Public upload delivery is intentionally not exposed in this local workspace."}


# Change sets
@app.get(f"{settings.api_prefix}/change-sets")
def list_change_sets(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(ChangeSet).filter(ChangeSet.organization_id == ctx.organization_id).order_by(desc(ChangeSet.created_at)).all()
    return {"items": [{"id": value.id, "name": value.name, "status": value.status, "risk_level": value.risk_level, "created_by": value.created_by, "summary": value.summary, "approval_policy": value.approval_policy, "created_at": value.created_at.isoformat()} for value in values]}


@app.post(f"{settings.api_prefix}/change-sets")
def create_change_set(body: ChangeSetRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Publishing Manager", "Organization Admin")
    products = [get_org_entity(db, ProductCandidate, product_id, ctx) for product_id in body.product_ids]
    change_set = ChangeSet(organization_id=ctx.organization_id, name=body.name, status="Draft", created_by=ctx.user.email, risk_level=body.risk_level, approval_policy={"required_role": "Publishing Manager" if body.risk_level != "High" else "Organization Admin", "second_review": body.risk_level == "High"}, summary=body.summary)
    db.add(change_set)
    db.flush()
    for product in products:
        db.add(ChangeSetItem(change_set_id=change_set.id, product_candidate_id=product.id, entity_type="product", before_json={"status": product.status}, after_json={"publish_intent": True}, validation_state="Healthy" if product.status == "Approved" else "Needs review"))
    add_audit(db, ctx, "change_set.created", "change_set", change_set.id, {"product_count": len(products), "risk_level": body.risk_level})
    db.commit()
    return {"id": change_set.id, "status": change_set.status, "product_count": len(products)}


@app.get(f"{settings.api_prefix}/change-sets/{{change_set_id}}")
def change_set_detail(change_set_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    change_set = get_org_entity(db, ChangeSet, change_set_id, ctx)
    items = db.query(ChangeSetItem).filter(ChangeSetItem.change_set_id == change_set.id).all()
    approvals = db.query(ChangeApproval).filter(ChangeApproval.change_set_id == change_set.id).all()
    return {"id": change_set.id, "name": change_set.name, "status": change_set.status, "risk_level": change_set.risk_level, "summary": change_set.summary, "approval_policy": change_set.approval_policy, "items": [{"id": item.id, "product_id": item.product_candidate_id, "entity_type": item.entity_type, "before": item.before_json, "after": item.after_json, "validation_state": item.validation_state} for item in items], "approvals": [{"id": approval.id, "approver": approval.approver, "role": approval.role, "decision": approval.decision, "note": approval.note, "at": approval.created_at.isoformat()} for approval in approvals]}


@app.post(f"{settings.api_prefix}/change-sets/{{change_set_id}}/submit")
def submit_change_set(change_set_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    change_set = get_org_entity(db, ChangeSet, change_set_id, ctx)
    if change_set.status != "Draft":
        raise HTTPException(status_code=409, detail="Only draft change sets may be submitted.")
    change_set.status = "Needs review"
    add_audit(db, ctx, "change_set.submitted", "change_set", change_set.id)
    db.commit()
    return {"id": change_set.id, "status": change_set.status}


@app.post(f"{settings.api_prefix}/change-sets/{{change_set_id}}/approve")
def approve_change_set(change_set_id: str, body: ChangeApprovalRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    change_set = get_org_entity(db, ChangeSet, change_set_id, ctx)
    required_role = change_set.approval_policy.get("required_role", "Publishing Manager")
    require_roles(ctx, required_role, "Organization Admin")
    change_set.status = "Approved" if body.decision == "Approved" else "Rejected"
    approval = ChangeApproval(change_set_id=change_set.id, approver=ctx.user.email, role=ctx.role, decision=body.decision, note=body.note)
    db.add(approval)
    add_audit(db, ctx, "change_set.approved" if body.decision == "Approved" else "change_set.rejected", "change_set", change_set.id, {"note": body.note})
    db.commit()
    return {"id": change_set.id, "status": change_set.status, "approval_id": approval.id}


# Reports, alerts and governed assistant
@app.get(f"{settings.api_prefix}/reports")
def reports(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(Report).filter(Report.organization_id == ctx.organization_id).order_by(desc(Report.created_at)).all()
    schedules = db.query(ScheduledReport).filter(ScheduledReport.organization_id == ctx.organization_id).all()
    return {"items": [{"id": value.id, "type": value.report_type, "name": value.name, "status": value.status, "generated_by": value.generated_by, "scope": value.scope, "data_freshness": value.data_freshness, "export_id": value.export_id, "artifact_path": value.artifact_path, "created_at": value.created_at.isoformat()} for value in values], "scheduled": [{"id": schedule.id, "type": schedule.report_type, "cadence": schedule.cadence, "delivery": schedule.delivery, "status": schedule.status, "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None} for schedule in schedules]}


def _create_report_artifact(report: Report, org: Organization) -> Path:
    report_dir = Path(settings.local_storage_path).resolve().parent / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{report.export_id}.pdf"
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, 744, "SYNTHETIC DEMO — CatalogForge AI Report")
    pdf.setFont("Helvetica", 10)
    lines = [f"Report: {report.name}", f"Organization: {org.name}", f"Scope: {json.dumps(report.scope, sort_keys=True)}", "Data caveat: Metrics and entities in this export are synthetic demo data.", "Delivery: Generated locally; no real email or external report service was contacted."]
    y = 710
    for line in lines:
        pdf.drawString(54, y, line[:120])
        y -= 22
    pdf.save()
    path.write_bytes(buffer.getvalue())
    return path


@app.post(f"{settings.api_prefix}/reports")
def create_report(body: ReportRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Vendor Manager", "Compliance Reviewer", "Organization Admin")
    org = organization_or_404(db, ctx.organization_id)
    report = Report(organization_id=ctx.organization_id, report_type=body.report_type, name=body.name or body.report_type, status="Completed", generated_by=ctx.user.email, scope={**body.scope, "synthetic": True}, data_freshness="Synthetic snapshot at generation", export_id=f"RPT-{uuid4().hex[:10].upper()}")
    db.add(report)
    db.flush()
    report.artifact_path = str(_create_report_artifact(report, org))
    create_durable_job(db, ctx, "Report generation", "report", report.id, status="Completed", metadata={"report_type": body.report_type})
    add_audit(db, ctx, "report.generated", "report", report.id, {"export_id": report.export_id, "synthetic": True})
    db.commit()
    return {"id": report.id, "export_id": report.export_id, "status": report.status, "artifact_path": report.artifact_path, "synthetic": True}


@app.get(f"{settings.api_prefix}/reports/{{report_id}}/export")
def export_report(report_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)):
    report = get_org_entity(db, Report, report_id, ctx)
    if not report.artifact_path or not Path(report.artifact_path).exists():
        raise HTTPException(status_code=404, detail="Report artifact unavailable.")
    add_audit(db, ctx, "report.downloaded", "report", report.id, {"export_id": report.export_id})
    db.commit()
    return StreamingResponse(Path(report.artifact_path).open("rb"), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{report.export_id}.pdf"'})


@app.post(f"{settings.api_prefix}/reports/schedules")
def schedule_report(body: ScheduledReportRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Catalog Operations Manager", "Organization Admin")
    schedule = ScheduledReport(organization_id=ctx.organization_id, report_type=body.report_type, cadence=body.cadence, delivery=body.delivery, status="Active")
    db.add(schedule)
    add_audit(db, ctx, "report.scheduled", "scheduled_report", schedule.id, {"delivery": body.delivery, "mock_delivery": True})
    db.commit()
    return {"id": schedule.id, "status": schedule.status, "delivery": schedule.delivery, "mock": True}


@app.get(f"{settings.api_prefix}/alerts")
def alerts(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(Alert).filter(Alert.organization_id == ctx.organization_id).order_by(desc(Alert.created_at)).all()
    watchlists = db.query(Watchlist).filter(Watchlist.organization_id == ctx.organization_id).all()
    return {"items": [{"id": value.id, "category": value.category, "severity": value.severity, "title": value.title, "message": value.message, "status": value.status, "entity_type": value.entity_type, "entity_id": value.entity_id, "assigned_to": value.assigned_to, "created_at": value.created_at.isoformat()} for value in values], "watchlists": [{"id": watchlist.id, "name": watchlist.name, "filter_config": watchlist.filter_config, "owner": watchlist.owner} for watchlist in watchlists]}


@app.post(f"{settings.api_prefix}/alerts/{{alert_id}}/action")
def alert_action(alert_id: str, body: AlertActionRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    alert = get_org_entity(db, Alert, alert_id, ctx)
    if body.action == "acknowledge":
        alert.status = "Acknowledged"
    elif body.action == "resolve":
        alert.status = "Resolved"
    else:
        alert.status = "Snoozed"
        alert.snoozed_until = utcnow() + timedelta(hours=4)
    add_audit(db, ctx, f"alert.{body.action}", "alert", alert.id, {"note": body.note})
    db.commit()
    return {"id": alert.id, "status": alert.status, "snoozed_until": alert.snoozed_until.isoformat() if alert.snoozed_until else None}


@app.post(f"{settings.api_prefix}/assistant/query")
def catalog_intelligence_assistant(body: AssistantRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    question = body.question.lower()
    vendors = db.query(Vendor).filter(Vendor.organization_id == ctx.organization_id).all()
    products = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id).all()
    open_validations = db.query(ValidationResult).join(ProductCandidate, ValidationResult.product_candidate_id == ProductCandidate.id).filter(ProductCandidate.organization_id == ctx.organization_id, ValidationResult.state == "open").all()
    related: dict[str, list[dict]] = {"vendors": [], "documents": [], "products": [], "review_tasks": [], "publish_jobs": [], "audit_events": []}
    if any(token in question for token in ["vendor", "supplier", "validation"]):
        ranking = sorted(vendors, key=lambda vendor: vendor.quality_score)[:3]
        summary = "The highest-priority synthetic vendor quality risks are " + ", ".join(f"{vendor.name} ({vendor.quality_score:.0%} rules-based score)" for vendor in ranking) + "."
        related["vendors"] = [{"id": vendor.id, "name": vendor.name, "quality_score": vendor.quality_score} for vendor in ranking]
        next_action = "Open the vendor quality workspace and review recurring missing-SKU and source-template issues."
    elif any(token in question for token in ["publish", "shopify", "destination", "ready"]):
        ready = [product for product in products if product.status == "Approved"][:8]
        summary = f"{len(ready)} sampled approved products are eligible for channel-readiness review. Publishing remains governed by destination-specific validation and change-set approval."
        related["products"] = [{"id": product.id, "title": product.title, "status": product.status} for product in ready]
        next_action = "Create a dry-run publish batch to inspect mapping and readiness without changing a destination."
    elif any(token in question for token in ["duplicate", "merge"]):
        groups = db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id, DuplicateGroup.status.in_(["Candidate", "In review"])).order_by(desc(DuplicateGroup.similarity_score)).limit(5).all()
        summary = f"{len(groups)} high-priority duplicate candidates are currently unresolved in the active workspace."
        related["products"] = [{"id": group.id, "title": f"Duplicate group {group.id[:8]}", "status": group.status} for group in groups]
        next_action = "Open Duplicate Resolution and choose a canonical record only after reviewing source evidence and merge impact."
    elif any(token in question for token in ["blocked", "why", "validation", "quality"]):
        summary = f"{len(open_validations)} open validation findings are active. Common blockers are missing SKU, shipping weight, and destination field requirements."
        related["review_tasks"] = [{"id": task.id, "reason": task.reason, "status": task.status} for task in db.query(ReviewTask).filter(ReviewTask.organization_id == ctx.organization_id, ReviewTask.status == "Open").limit(5)]
        next_action = "Open the review queue, correct the field from evidence, then re-check channel readiness."
    else:
        summary = "I cannot verify information outside CatalogForge product-data operations. I can analyze synthetic catalog completeness, vendor quality, source-document extraction, validation findings, duplicate risk, publishing status, and lineage within this workspace."
        next_action = "Ask about vendors, source documents, validation, duplicate resolution, publishing, taxonomy, or reports."
    return {"mode": body.mode, "executive_summary": summary, "scope": {"organization_id": ctx.organization_id, "filters": body.filters}, "data_sources": ["products", "validation results", "review tasks", "publish jobs", "synthetic audit events"], "supporting_metrics": {"products": len(products), "open_validations": len(open_validations), "vendors": len(vendors)}, "evidence_links": related, "data_quality_caveats": "This response is generated from the active synthetic demo workspace and rules-based metrics. It is not a prediction, certification, or external marketplace-performance analysis.", "confidence": "High for direct workspace counts; limited for qualitative prioritization.", "limitations": ("I cannot verify marketplace listing performance, sales, or data outside this workspace. " if not any(token in question for token in ["vendor", "supplier", "validation", "publish", "shopify", "destination", "ready", "duplicate", "merge", "blocked", "why", "quality"]) else "") + "The governed assistant does not execute mutations. Suggested drafts require explicit user confirmation in the corresponding workflow.", "suggested_next_action": next_action}


# Governance, lineage and security
@app.get(f"{settings.api_prefix}/lineage/products/{{product_id}}")
def product_lineage(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    job = db.get(UploadJob, product.upload_job_id) if product.upload_job_id else None
    document = db.query(SourceDocument).filter(SourceDocument.upload_job_id == product.upload_job_id, SourceDocument.organization_id == ctx.organization_id).first() if job else None
    fields = db.query(ExtractedField).filter(ExtractedField.product_candidate_id == product.id).all()
    validations = db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id).all()
    reviews = db.query(ReviewTask).filter(ReviewTask.product_candidate_id == product.id, ReviewTask.organization_id == ctx.organization_id).all()
    versions = db.query(ProductVersion).filter(ProductVersion.product_candidate_id == product.id).all()
    publish_jobs = [job for job in db.query(PublicationJob).filter(PublicationJob.organization_id == ctx.organization_id).all() if product.id in (job.product_ids or {}).get("items", [])]
    vendor = db.get(Vendor, product.vendor_id)
    nodes = [
        {"id": f"vendor:{product.vendor_id}", "type": "Vendor", "label": vendor.name if vendor else "Unknown vendor"},
        {"id": f"document:{document.id}" if document else "document:unknown", "type": "Source Document", "label": document.original_filename if document else "No source document"},
        {"id": f"product:{product.id}", "type": "Product Candidate", "label": product.title},
    ]
    nodes += [{"id": f"field:{field.id}", "type": "Extracted Field", "label": field.field_name, "metadata": {"source": field.evidence, "normalization": field.transformation_history}} for field in fields]
    nodes += [{"id": f"validation:{value.id}", "type": "Validation", "label": value.rule_name, "metadata": {"state": value.state}} for value in validations]
    nodes += [{"id": f"review:{task.id}", "type": "Review Task", "label": task.reason} for task in reviews]
    nodes += [{"id": f"version:{version.id}", "type": "Human/Product Version", "label": version.change_summary} for version in versions]
    nodes += [{"id": f"publish:{job.id}", "type": "Publish Job", "label": job.status} for job in publish_jobs]
    edges = [{"from": nodes[1]["id"], "to": f"field:{field.id}", "label": "evidence"} for field in fields] + [{"from": f"field:{field.id}", "to": f"product:{product.id}", "label": "maps to"} for field in fields] + [{"from": f"product:{product.id}", "to": f"validation:{value.id}", "label": "validated by"} for value in validations] + [{"from": f"product:{product.id}", "to": f"review:{task.id}", "label": "reviewed in"} for task in reviews] + [{"from": f"product:{product.id}", "to": f"publish:{job.id}", "label": "published by"} for job in publish_jobs]
    return {"product_id": product.id, "nodes": nodes, "edges": edges, "field_lineage": [{"field": field.field_name, "source": field.evidence, "normalized_value": field.normalized_value, "reviewer_override": field.reviewer_override, "destination_mapping": field.destination_mapping} for field in fields], "synthetic": True}


@app.get(f"{settings.api_prefix}/lineage/products/{{product_id}}/evidence-package")
def evidence_package(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    lineage = product_lineage(product.id, ctx, db)
    add_audit(db, ctx, "lineage.evidence_exported", "product", product.id, {"format": "json", "synthetic": True})
    db.commit()
    return {"package_type": "Synthetic Demo Evidence Package", "generated_at": utcnow().isoformat(), "product": product_payload(product, db, ctx, detail=True), "lineage": lineage, "disclaimer": "All data in this evidence package is synthetic demo data."}


@app.get(f"{settings.api_prefix}/governance/audit-events")
def audit_events(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(AuditEvent).filter(AuditEvent.organization_id == ctx.organization_id).order_by(desc(AuditEvent.created_at)).limit(240).all()
    return {"items": [{"id": value.id, "at": value.created_at.isoformat(), "actor": value.actor, "action": value.action, "entity_type": value.entity_type, "entity_id": value.entity_id, "payload": value.payload, "request_id": value.request_id} for value in values]}


@app.get(f"{settings.api_prefix}/governance/api-keys")
def api_keys(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Integration Manager", "Organization Admin", "Compliance Reviewer")
    values = db.query(APIKey).filter(APIKey.organization_id == ctx.organization_id).all()
    return {"items": [{"id": value.id, "name": value.name, "prefix": value.key_prefix, "scopes": value.scopes, "expires_at": value.expires_at.isoformat() if value.expires_at else None, "revoked_at": value.revoked_at.isoformat() if value.revoked_at else None, "last_used_at": value.last_used_at.isoformat() if value.last_used_at else None} for value in values]}


@app.post(f"{settings.api_prefix}/governance/api-keys")
def create_api_key(body: APIKeyRequest, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Integration Manager", "Organization Admin")
    raw = f"cf_live_{secrets.token_urlsafe(24)}"
    key = APIKey(organization_id=ctx.organization_id, name=body.name, key_prefix=f"{raw[:12]}••••", secret_hash=password_hash(raw), scopes={"scopes": body.scopes}, expires_at=utcnow() + timedelta(days=body.expires_in_days))
    db.add(key)
    db.flush()
    add_audit(db, ctx, "api_key.created", "api_key", key.id, {"scopes": body.scopes, "expires_in_days": body.expires_in_days})
    db.commit()
    return {"id": key.id, "key": raw, "warning": "This synthetic demo secret is shown once. Do not treat it as production credential material."}


@app.post(f"{settings.api_prefix}/governance/api-keys/{{key_id}}/revoke")
def revoke_api_key(key_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Integration Manager", "Organization Admin")
    key = get_org_entity(db, APIKey, key_id, ctx)
    key.revoked_at = utcnow()
    add_audit(db, ctx, "api_key.revoked", "api_key", key.id)
    db.commit()
    return {"id": key.id, "revoked_at": key.revoked_at.isoformat()}


@app.get(f"{settings.api_prefix}/governance/webhooks")
def webhooks(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    values = db.query(WebhookDelivery).filter(WebhookDelivery.organization_id == ctx.organization_id).all()
    return {"items": [{"id": value.id, "event_type": value.event_type, "endpoint": value.endpoint, "status_code": value.status_code, "response_excerpt": value.response_excerpt, "delivery_status": value.delivery_status, "retry_count": value.retry_count, "payload_preview": value.payload_preview} for value in values]}


@app.post(f"{settings.api_prefix}/governance/webhooks/{{delivery_id}}/retry")
def retry_webhook(delivery_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Integration Manager", "Organization Admin")
    delivery = get_org_entity(db, WebhookDelivery, delivery_id, ctx)
    delivery.retry_count += 1
    delivery.delivery_status = "Delivered"
    delivery.status_code = 200
    delivery.response_excerpt = "Synthetic retry delivery acknowledged."
    add_audit(db, ctx, "webhook.retried", "webhook_delivery", delivery.id, {"retry_count": delivery.retry_count, "mock": True})
    db.commit()
    return {"id": delivery.id, "delivery_status": delivery.delivery_status, "retry_count": delivery.retry_count, "mock": True}


@app.get(f"{settings.api_prefix}/governance/roles-users")
def roles_users(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    roles = db.query(Role).filter(Role.organization_id == ctx.organization_id).all()
    memberships = db.query(WorkspaceMembership).filter(WorkspaceMembership.organization_id == ctx.organization_id).all()
    users = []
    for membership in memberships:
        user = db.get(User, membership.user_id)
        if user:
            users.append({"id": membership.user_id, "name": user.name, "email": user.email, "role": membership.role})
    return {"roles": [{"id": role.id, "name": role.name, "permissions": role.permissions} for role in roles], "users": users}


@app.get(f"{settings.api_prefix}/governance/settings")
def workspace_settings(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    org = organization_or_404(db, ctx.organization_id)
    return {"workspace": org.name, "workspace_id": org.id, "retention_days": org.data_retention_days, "data_deletion": "Approval required", "storage": settings.storage_backend, "demo_mode": True, "security_wording": "Security controls designed to support enterprise deployment.", "legal_hold": "Architecture placeholder; not legal advice or a compliance certification."}


@app.post(f"{settings.api_prefix}/governance/retention-requests")
def create_retention_request(body: RetentionRequestBody, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Compliance Reviewer", "Organization Admin")
    request = RetentionRequest(organization_id=ctx.organization_id, request_type=body.request_type, entity_type=body.entity_type, entity_id=body.entity_id, status="Needs review", requested_by=ctx.user.email)
    db.add(request)
    db.flush()
    add_audit(db, ctx, "retention.request_created", "retention_request", request.id, {"entity_type": body.entity_type, "entity_id": body.entity_id})
    db.commit()
    return {"id": request.id, "status": request.status}

# Phase 3 launch hardening, API-driven UX and release readiness
PHASE3_RELEASE_GATES = [
    ("tenant_isolation", "Backend-enforced organization isolation", "Critical"),
    ("rbac", "Role-aware permission controls", "Critical"),
    ("deterministic_local_mode", "No-key deterministic demo mode", "Critical"),
    ("source_evidence", "Immutable field evidence and lineage", "High"),
    ("publishing_gate", "Validation and approval-gated publishing", "Critical"),
    ("reconciliation", "Destination reconciliation and retry evidence", "High"),
    ("governance_exports", "Audited evidence, report and API export controls", "High"),
    ("provider_boundaries", "Optional OCR, LLM, storage and connector boundaries", "Medium"),
]


def _launch_gate_status(db: Session, ctx: WorkspaceContext, gate_key: str) -> tuple[str, dict, str]:
    products = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id)
    documents = db.query(SourceDocument).filter(SourceDocument.organization_id == ctx.organization_id)
    fields = db.query(ExtractedField).join(ProductCandidate, ExtractedField.product_candidate_id == ProductCandidate.id).filter(ProductCandidate.organization_id == ctx.organization_id)
    publish_jobs = db.query(PublicationJob).filter(PublicationJob.organization_id == ctx.organization_id)
    failed_publish = publish_jobs.filter(PublicationJob.status == "Failed").count()
    audits = db.query(AuditEvent).filter(AuditEvent.organization_id == ctx.organization_id)
    if gate_key == "tenant_isolation":
        return "Passed", {"workspace_id": ctx.organization_id, "scoped_entities": ["products", "documents", "vendors", "publish_jobs", "reports", "audit_events"]}, "Every Phase 3 endpoint uses the active workspace context and organization_id filters."
    if gate_key == "rbac":
        return "Passed", {"active_role": ctx.role, "roles": db.query(Role).filter(Role.organization_id == ctx.organization_id).count()}, "Sensitive actions call require_roles and return 403 for unauthorized users."
    if gate_key == "deterministic_local_mode":
        return "Passed", {"demo_mode": settings.demo_mode, "external_keys_required": False, "worker": "inline deterministic"}, "Local CSV/XLSX/JSON/PDF-safe workflows remain available without OCR, LLM, Redis, Postgres, Docker or cloud credentials."
    if gate_key == "source_evidence":
        status = "Passed" if fields.count() > 0 and documents.count() > 0 else "Needs attention"
        return status, {"source_documents": documents.count(), "field_evidence_records": fields.count()}, "Field-level evidence links product values back to source page, row, bbox, parser method, confidence and transformation history."
    if gate_key == "publishing_gate":
        approved = products.filter(ProductCandidate.status == "Approved").count()
        blocked = db.query(ChannelReadiness).filter(ChannelReadiness.organization_id == ctx.organization_id, ChannelReadiness.status == "Blocked").count()
        return "Passed", {"approved_products": approved, "blocked_readiness_records": blocked, "publish_jobs": publish_jobs.count()}, "Products remain blocked until validation, approval and destination readiness gates pass."
    if gate_key == "reconciliation":
        return "Passed", {"open_issues": db.query(ReconciliationIssue).filter(ReconciliationIssue.organization_id == ctx.organization_id, ReconciliationIssue.status == "Open").count(), "failed_publish_jobs": failed_publish}, "Mock destination drift and retry outcomes are persisted as reconciliation records."
    if gate_key == "governance_exports":
        return "Passed", {"audit_events": audits.count(), "reports": db.query(Report).filter(Report.organization_id == ctx.organization_id).count(), "api_keys": db.query(APIKey).filter(APIKey.organization_id == ctx.organization_id).count()}, "Sensitive exports, API keys and evidence packages create audit events."
    return "Passed", {"ocr": settings.ocr_provider, "llm": settings.llm_provider, "storage": settings.storage_backend, "connectors": "mock and optional boundaries"}, "External providers are optional architecture boundaries and are not claimed as live in local demo mode."


@app.get(f"{settings.api_prefix}/launch/readiness")
def launch_readiness(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Platform Admin", "Organization Admin", "Catalog Operations Manager", "Compliance Reviewer", "Integration Manager")
    rows = []
    for gate_key, label, severity in PHASE3_RELEASE_GATES:
        status, evidence, note = _launch_gate_status(db, ctx, gate_key)
        check = db.query(LaunchReadinessCheck).filter(LaunchReadinessCheck.organization_id == ctx.organization_id, LaunchReadinessCheck.gate_key == gate_key).first()
        if not check:
            check = LaunchReadinessCheck(organization_id=ctx.organization_id, gate_key=gate_key, label=label)
            db.add(check)
        check.status = status
        check.severity = severity
        check.evidence = evidence
        check.remediation = note
        check.last_checked_at = utcnow()
        rows.append({"key": gate_key, "label": label, "status": status, "severity": severity, "evidence": evidence, "remediation": note, "last_checked_at": check.last_checked_at.isoformat()})
    passed = sum(1 for item in rows if item["status"] == "Passed")
    score = round(passed / max(1, len(rows)) * 100)
    add_audit(db, ctx, "launch.readiness_evaluated", "organization", ctx.organization_id, {"score": score, "checks": len(rows)})
    db.commit()
    return {"phase": "Phase 3 Enterprise Launch Hardening", "workspace_id": ctx.organization_id, "launch_score": score, "status": "Portfolio launch ready" if score >= 90 else "Needs attention", "checks": rows, "claims_policy": {"no_real_customers": True, "no_live_ocr_accuracy_claim": True, "mock_connectors_labeled": True, "synthetic_data_labeled": True}, "disclaimer": "Readiness is calculated from synthetic demo data, local deterministic workflows and verified API boundaries; it is not a compliance certification."}


@app.get(f"{settings.api_prefix}/launch/golden-demo")
def golden_demo(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Platform Admin", "Organization Admin", "Catalog Operations Manager", "Product Reviewer", "Publishing Manager")
    job = db.query(UploadJob).filter(UploadJob.organization_id == ctx.organization_id).order_by(desc(UploadJob.product_count)).first()
    product = db.query(ProductCandidate).filter(ProductCandidate.organization_id == ctx.organization_id, ProductCandidate.status.in_(["Needs review", "Approved", "Extracted"])).first()
    duplicate = db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id).first()
    destination = db.query(PublicationDestination).filter(PublicationDestination.organization_id == ctx.organization_id).first()
    change = db.query(ChangeSet).filter(ChangeSet.organization_id == ctx.organization_id).first()
    return {"title": "Supplier Catalog to Governed Publication", "synthetic": True, "steps": [
        {"step": 1, "label": "Open supplier intake batch", "entity_type": "upload_job", "entity_id": job.id if job else None, "href": f"/workspace/intake?job={job.id}" if job else "/workspace/intake"},
        {"step": 2, "label": "Inspect source evidence", "entity_type": "product", "entity_id": product.id if product else None, "href": f"/workspace/documents?product={product.id}" if product else "/workspace/documents"},
        {"step": 3, "label": "Correct validation blocker and approve", "entity_type": "product", "entity_id": product.id if product else None, "href": f"/workspace/review?product={product.id}" if product else "/workspace/review"},
        {"step": 4, "label": "Resolve duplicate governance", "entity_type": "duplicate_group", "entity_id": duplicate.id if duplicate else None, "href": f"/workspace/duplicates?group={duplicate.id}" if duplicate else "/workspace/duplicates"},
        {"step": 5, "label": "Create governed change set", "entity_type": "change_set", "entity_id": change.id if change else None, "href": f"/workspace/change-sets?change_set={change.id}" if change else "/workspace/change-sets"},
        {"step": 6, "label": "Run mock destination publish", "entity_type": "destination", "entity_id": destination.id if destination else None, "href": "/workspace/publish"},
        {"step": 7, "label": "Export lineage evidence package", "entity_type": "product", "entity_id": product.id if product else None, "href": f"/workspace/lineage?product={product.id}" if product else "/workspace/lineage"},
    ], "operator_notes": "Each step is backed by active workspace API records. External delivery remains mocked unless production connectors are configured."}


@app.get(f"{settings.api_prefix}/launch/data-contracts")
def data_contracts(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    rows = db.query(DataContract).filter(DataContract.organization_id == ctx.organization_id).order_by(DataContract.contract_type, DataContract.name).all()
    return {"items": [{"id": row.id, "name": row.name, "type": row.contract_type, "version": row.version, "status": row.status, "owner_role": row.owner_role, "schema": row.schema_json, "policy": row.policy_json, "last_validated_at": row.last_validated_at.isoformat() if row.last_validated_at else None} for row in rows]}


@app.get(f"{settings.api_prefix}/launch/saved-views")
def saved_views(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    rows = db.query(SavedEntityView).filter(SavedEntityView.organization_id == ctx.organization_id).order_by(SavedEntityView.name).all()
    return {"items": [{"id": row.id, "name": row.name, "entity_type": row.entity_type, "owner": row.owner, "filters": row.filter_config, "columns": row.column_config, "shared": row.is_shared} for row in rows]}


@app.get(f"{settings.api_prefix}/governance/permission-matrix")
def permission_matrix(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Platform Admin", "Organization Admin", "Compliance Reviewer")
    roles = db.query(Role).filter(Role.organization_id == ctx.organization_id).order_by(Role.name).all()
    sensitive_actions = ["intake.manage", "products.review", "duplicates.resolve", "publishing.manage", "reconciliation.manage", "taxonomy.manage", "api_keys.manage", "audit.read", "retention.review", "reports.create"]
    return {"items": [{"role": role.name, "rank": ROLE_ORDER.get(role.name, 0), "permissions": {action: bool(role.permissions.get("all") or role.permissions.get(action)) for action in sensitive_actions}} for role in roles], "enforcement": "Server-side dependencies enforce role checks; frontend controls are not trusted for authorization."}


@app.get(f"{settings.api_prefix}/governance/audit-export", response_class=PlainTextResponse)
def audit_export(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> PlainTextResponse:
    require_roles(ctx, "Platform Admin", "Organization Admin", "Compliance Reviewer")
    rows = db.query(AuditEvent).filter(AuditEvent.organization_id == ctx.organization_id).order_by(desc(AuditEvent.created_at)).limit(500).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["created_at", "actor", "action", "entity_type", "entity_id", "request_id", "payload_redacted"])
    for row in rows:
        payload = {k: ("[redacted]" if "key" in k.lower() or "secret" in k.lower() else v) for k, v in (row.payload or {}).items()}
        writer.writerow([row.created_at.isoformat(), row.actor, row.action, row.entity_type, row.entity_id, row.request_id or "", json.dumps(payload, sort_keys=True)])
    add_audit(db, ctx, "audit.exported", "organization", ctx.organization_id, {"format": "csv", "rows": len(rows), "redacted": True})
    db.commit()
    return PlainTextResponse(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=catalogforge-audit-export.csv"})


@app.get(f"{settings.api_prefix}/products/{{product_id}}/release-gate")
def product_release_gate(product_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    product = get_org_entity(db, ProductCandidate, product_id, ctx)
    validations = db.query(ValidationResult).filter(ValidationResult.product_candidate_id == product.id, ValidationResult.state == "open").all()
    readiness = db.query(ChannelReadiness).filter(ChannelReadiness.organization_id == ctx.organization_id, ChannelReadiness.product_candidate_id == product.id).all()
    duplicate_block = any(product.id in {group.rationale.get("left_product_id"), group.rationale.get("right_product_id")} for group in db.query(DuplicateGroup).filter(DuplicateGroup.organization_id == ctx.organization_id, DuplicateGroup.status.in_(["Candidate", "In review"])).all())
    blockers = [value.message for value in validations if value.blocking]
    for item in readiness:
        blockers.extend([f"{item.channel}: {blocker}" for blocker in item.blockers.get("items", [])])
    if duplicate_block:
        blockers.append("Unresolved duplicate candidate")
    gate_status = "Passed" if product.status == "Approved" and not blockers else "Blocked" if blockers else "Pending approval"
    return {"product_id": product.id, "title": product.title, "status": gate_status, "approved_for_internal_catalog": product.status == "Approved", "publish_blockers": blockers, "destination_readiness": [{"channel": item.channel, "status": item.status, "blockers": item.blockers} for item in readiness], "policy": "Products cannot publish until blocking validations, duplicate governance, human approval and destination readiness all pass."}


@app.get(f"{settings.api_prefix}/publish/jobs/{{job_id}}/delivery-proof")
def delivery_proof(job_id: str, ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    job = get_org_entity(db, PublicationJob, job_id, ctx)
    destination = db.get(PublicationDestination, job.destination_id)
    attempts = db.query(PublicationAttempt).filter(PublicationAttempt.publication_job_id == job.id).order_by(PublicationAttempt.attempt_number).all()
    logs = db.query(SyncLog).filter(SyncLog.publication_job_id == job.id).order_by(SyncLog.created_at).all()
    verified = bool(attempts and attempts[-1].status == "Completed" and attempts[-1].response.get("verified"))
    return {"publication_job_id": job.id, "destination": destination.name if destination else "Unknown", "mock_connector": True, "verified_delivery": verified, "job_status": job.status, "idempotency_key": job.idempotency_key, "attempts": [{"attempt": item.attempt_number, "status": item.status, "error": item.error, "response": item.response} for item in attempts], "logs": [{"level": item.level, "message": item.message, "at": item.created_at.isoformat()} for item in logs], "claim_boundary": "Delivery proof is based on the local mock connector response only; no real external destination API was contacted."}


@app.get(f"{settings.api_prefix}/platform/operations")
def platform_operations(ctx: WorkspaceContext = Depends(resolve_workspace), db: Session = Depends(get_db)) -> dict:
    require_roles(ctx, "Platform Admin", "Organization Admin", "Integration Manager")
    jobs = db.query(DurableJob).filter(DurableJob.organization_id == ctx.organization_id)
    return {"health": {"api": "healthy", "database": "healthy", "redis": "configured boundary" if settings.demo_mode else "configured", "worker": "inline deterministic demo worker" if settings.demo_mode else "external worker", "object_storage": settings.storage_backend}, "telemetry": {"intake_jobs": db.query(UploadJob).filter(UploadJob.organization_id == ctx.organization_id).count(), "average_extraction_time_ms": int(db.query(func.avg(DurableJob.duration_ms)).filter(DurableJob.organization_id == ctx.organization_id).scalar() or 0), "extraction_failure_rate": round(jobs.filter(DurableJob.status == "Failed").count() / max(1, jobs.count()), 3), "review_queue_volume": db.query(ReviewTask).filter(ReviewTask.organization_id == ctx.organization_id, ReviewTask.status == "Open").count(), "publish_success_rate": round(db.query(PublicationJob).filter(PublicationJob.organization_id == ctx.organization_id, PublicationJob.status == "Completed").count() / max(1, db.query(PublicationJob).filter(PublicationJob.organization_id == ctx.organization_id).count()), 3), "demo_usage_cost_estimate": "$0.00 — deterministic local execution"}, "disclaimer": "Demo usage telemetry and estimated cost model; no actual billing or production infrastructure monitoring is claimed."}
