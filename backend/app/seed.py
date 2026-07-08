from __future__ import annotations

import csv
import hashlib
import os
import random
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (
    Alert,
    APIKey,
    DataContract,
    AttributeDefinition,
    AttributeValue,
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
    LaunchReadinessCheck,
    ExtractionJob,
    JobEvent,
    OCRBlock,
    Organization,
    ProductCandidate,
    ProductImage,
    ProductRecord,
    ProductVersion,
    PublicationAttempt,
    PublicationDestination,
    PublicationJob,
    ReconciliationIssue,
    Report,
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
from .services.pipeline import completeness_score

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "pyproject.toml").exists() and Path("/workspace/demo_data").exists():
    ROOT = Path("/workspace")
DEMO = ROOT / "demo_data"
DOCS = DEMO / "source_documents"
IMAGES = DEMO / "product_images"
random.seed(42)

ORGANIZATIONS = [
    ("Northstar Commerce Group", "northstar-commerce"),
    ("Meridian Marketplace Operations", "meridian-marketplace"),
    ("Atlas Wholesale Distribution", "atlas-wholesale"),
]
VENDOR_NAMES = [
    "Northern Atelier", "Harbor & Field", "Alder Supply Co.", "Morrow Textiles",
    "Mason & Vale", "Terra Housewares", "Juniper Goods", "Lumen Living",
]
CATEGORIES = [
    "Home / Storage", "Home / Table Linen", "Kitchen / Serveware", "Kitchen / Boards",
    "Kitchen / Storage", "Lighting / Table Lamps", "Bath / Towels", "Office / Desk Accessories",
]
ADJECTIVES = ["Woven", "Linen", "Ceramic", "Oak", "Glass", "Cotton", "Brass", "Stoneware"]
NOUNS = ["Storage Basket", "Table Runner", "Pouring Bowl", "Serving Board", "Pantry Jar", "Napkin Set", "Table Lamp", "Desk Tray"]
ROLES = {
    "Platform Admin": {"all": True},
    "Organization Admin": {"workspace.manage": True, "users.manage": True, "integrations.manage": True, "audit.read": True},
    "Catalog Operations Manager": {"intake.manage": True, "review.manage": True, "approve": True, "reports.create": True},
    "Vendor Manager": {"vendors.manage": True, "templates.manage": True, "intake_links.manage": True},
    "Product Reviewer": {"products.review": True, "duplicates.resolve": True, "notes.write": True},
    "Taxonomy Manager": {"taxonomy.manage": True, "rules.manage": True},
    "Publishing Manager": {"publishing.manage": True, "reconciliation.manage": True},
    "Integration Manager": {"integrations.manage": True, "webhooks.manage": True, "api_keys.manage": True},
    "Compliance Reviewer": {"audit.read": True, "retention.review": True, "exports.review": True},
    "Viewer": {"read": True},
}
DEMO_ACCOUNTS = [
    ("admin@catalogforge.demo", "Avery Chen", "Organization Admin"),
    ("catalog.ops@catalogforge.demo", "Jordan Lee", "Catalog Operations Manager"),
    ("vendors@catalogforge.demo", "Morgan Patel", "Vendor Manager"),
    ("reviewer@catalogforge.demo", "Maya Torres", "Product Reviewer"),
    ("taxonomy@catalogforge.demo", "Rowan Kim", "Taxonomy Manager"),
    ("publishing@catalogforge.demo", "Priya Shah", "Publishing Manager"),
    ("integrations@catalogforge.demo", "Casey Nguyen", "Integration Manager"),
    ("compliance@catalogforge.demo", "Samira Khan", "Compliance Reviewer"),
    ("viewer@catalogforge.demo", "Alex Brooks", "Viewer"),
]


def password_hash(password: str, salt: str | None = None) -> str:
    """PBKDF2-SHA256 password hashing with per-user salt; no plaintext password is stored."""
    salt = salt or secrets.token_hex(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, digest = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        return secrets.compare_digest(candidate, digest)
    except ValueError:
        return False


def make_svg(path: Path, title: str, i: int) -> None:
    hue = ["#d7e5f2", "#e9d8cf", "#d6e4d4", "#efe2bd", "#e2d7e8"][i % 5]
    initial = title[:2].upper()
    path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
      <rect width="640" height="480" fill="#f6f1e8"/><rect x="44" y="42" width="552" height="396" rx="26" fill="{hue}"/>
      <path d="M210 310c0-86 49-144 110-144s110 58 110 144" fill="none" stroke="#202322" stroke-width="20" stroke-linecap="round"/>
      <rect x="238" y="234" width="164" height="116" rx="24" fill="#f9f7f1" stroke="#202322" stroke-width="10"/>
      <text x="320" y="408" text-anchor="middle" font-family="Arial" font-size="22" fill="#202322">SYNTHETIC • {initial}</text>
    </svg>''', encoding="utf-8")


def make_pdf(path: Path, title: str, products: int = 6) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    _, h = A4
    c.setFillColorRGB(0.12, 0.14, 0.13)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(48, h - 60, f"SYNTHETIC — {title}")
    c.setFont("Helvetica", 10)
    c.drawString(48, h - 82, "CatalogForge demo source document. No real supplier information.")
    for n in range(products):
        y = h - 130 - n * 72
        c.setFillColorRGB(0.9, 0.87, 0.80)
        c.rect(48, y - 42, 498, 54, fill=1, stroke=0)
        c.setFillColorRGB(0.12, 0.14, 0.13)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(62, y - 6, f"{ADJECTIVES[n % 8]} {NOUNS[n % 8]}")
        c.setFont("Helvetica", 9)
        c.drawString(62, y - 22, f"SKU: SYN-{n + 101:04d}     MSRP: ${18 + n * 7}.00     Material: Natural")
    c.showPage()
    c.save()


def make_csv(path: Path, vendor: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "sku", "brand", "category", "price", "inventory", "barcode", "material", "color", "weight", "dimensions"])
        writer.writeheader()
        for i in range(12):
            writer.writerow({"title": f"{ADJECTIVES[i % 8]} {NOUNS[i % 8]}", "sku": f"{vendor[:3].upper()}-{i + 201:04d}", "brand": vendor, "category": CATEGORIES[i % len(CATEGORIES)], "price": 18 + i * 4, "inventory": 10 + i * 4, "barcode": f"8901010{i:05d}", "material": "Natural fiber", "color": "Natural", "weight": "0.45 kg", "dimensions": "32 x 22 cm"})


def make_xlsx(path: Path, vendor: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["SKU", "Title", "Brand", "Category", "Price", "Inventory", "Barcode", "Material", "Color", "Weight", "Dimensions"])
    for i in range(10):
        ws.append([f"{vendor[:3].upper()}-{i + 301:04d}", f"{ADJECTIVES[i % 8]} {NOUNS[i % 8]}", vendor, CATEGORIES[i % len(CATEGORIES)], 22 + i * 3, 20 + i * 5, f"8901020{i:05d}", "Synthetic material", "Natural", "0.52 kg", "40 x 22 cm"])
    wb.save(path)


def ensure_source_files() -> list[tuple[str, str, str]]:
    DOCS.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[str, str, str]] = []
    for i in range(12):
        name = f"Synthetic_{VENDOR_NAMES[i % 8].replace(' ', '_').replace('&', 'and')}_Catalog_{i + 1:02d}.pdf"
        make_pdf(DOCS / name, f"{VENDOR_NAMES[i % 8]} Seasonal Catalog", 6)
        entries.append((name, VENDOR_NAMES[i % 8], "PDF catalog"))
    for i in range(10):
        name = f"Synthetic_vendor_export_{i + 1:02d}.csv"
        make_csv(DOCS / name, VENDOR_NAMES[i % 8])
        entries.append((name, VENDOR_NAMES[i % 8], "CSV"))
    for i in range(8):
        name = f"Synthetic_product_sheet_{i + 1:02d}.xlsx"
        make_xlsx(DOCS / name, VENDOR_NAMES[i])
        entries.append((name, VENDOR_NAMES[i], "Spreadsheet"))
    for i in range(10):
        name = f"Synthetic_{'Invoice' if i % 2 == 0 else 'Purchase_Order'}_{i + 1:02d}.pdf"
        make_pdf(DOCS / name, f"{VENDOR_NAMES[i % 8]} {'Invoice' if i % 2 == 0 else 'Purchase Order'}", 4)
        entries.append((name, VENDOR_NAMES[i % 8], "Invoice / PO"))
    for i in range(10):
        name = f"Synthetic_product_photo_batch_{i + 1:02d}.svg"
        make_svg(DOCS / name, f"Photo Batch {i + 1}", i)
        entries.append((name, VENDOR_NAMES[i % 8], "Image batch"))
    for i in range(60):
        make_svg(IMAGES / f"product_{i + 1:02d}.svg", f"Product {i + 1}", i)
    return entries


def add_audit(db: Session, org_id: str, actor: str, action: str, entity_type: str, entity_id: str, payload: dict) -> None:
    db.add(AuditEvent(organization_id=org_id, actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, payload=payload))


def _clear_demo(db: Session) -> None:
    # Safe only in synthetic local seed mode. Reverse dependency order avoids FK conflicts.
    tables = [
        "saved_entity_views", "data_contracts", "launch_readiness_checks", "retention_requests", "webhook_deliveries", "api_keys", "audit_events", "watchlists", "alerts", "scheduled_reports", "reports",
        "change_approvals", "change_set_items", "change_sets", "reconciliation_issues", "sync_logs", "publication_attempts", "publication_jobs",
        "publication_destinations", "reviewer_comments", "review_tasks", "duplicate_decisions", "duplicate_groups", "validation_results", "validation_rules",
        "attribute_values", "attribute_definitions", "categories", "channel_readiness", "product_versions", "product_records", "product_images",
        "extracted_fields", "product_candidates", "job_events", "durable_jobs", "extraction_jobs", "ocr_blocks", "source_pages", "source_documents",
        "upload_jobs", "vendor_intake_links", "vendor_templates", "vendors", "workspace_memberships", "roles", "users", "organizations",
    ]
    for table in tables:
        try:
            db.execute(text(f"DELETE FROM {table}"))
        except Exception:
            db.rollback()
    db.commit()


def seed(force: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    # Existing Phase 1 local SQLite demo databases can be safely regenerated as synthetic data.
    # Production upgrades are handled by Alembic before seeding.
    inspector = inspect(engine)
    if "organizations" in inspector.get_table_names() and "slug" not in {column["name"] for column in inspector.get_columns("organizations")}:
        if str(engine.url).startswith("sqlite"):
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
        else:
            raise RuntimeError("CatalogForge Phase 2 schema migration is required before seeding this database.")
    db = SessionLocal()
    try:
        current = db.query(Organization).count()
        phase2_ready = db.query(Organization).filter(Organization.slug == "northstar-commerce").first()
        if force or (current and not phase2_ready and os.getenv("CATALOGFORGE_RESET_SYNTHETIC", "0") == "1"):
            _clear_demo(db)
            current = 0
        if current and phase2_ready:
            return
        if current and not phase2_ready:
            # Existing Phase 1 demo is a synthetic dataset. Replace only the local demo schema after an explicit upgrade marker.
            _clear_demo(db)
        files = ensure_source_files()
        organizations: list[Organization] = []
        for name, slug in ORGANIZATIONS:
            org = Organization(name=name, slug=slug, is_synthetic=True, data_retention_days=90)
            db.add(org)
            db.flush()
            organizations.append(org)
            for role_name, permissions in ROLES.items():
                db.add(Role(organization_id=org.id, name=role_name, permissions=permissions))

        northstar = organizations[0]
        users: dict[str, User] = {}
        for email, name, role in DEMO_ACCOUNTS:
            user = User(organization_id=northstar.id, active_organization_id=northstar.id, email=email, name=name, role=role, password_hash=password_hash("DemoPass123!"))
            db.add(user)
            db.flush()
            users[email] = user
            db.add(WorkspaceMembership(user_id=user.id, organization_id=northstar.id, role=role, is_default=True))
        # The admin is a platform-level seeded operator; it can switch organizations. Other users are purposefully scoped to Northstar.
        for org in organizations[1:]:
            db.add(WorkspaceMembership(user_id=users["admin@catalogforge.demo"].id, organization_id=org.id, role="Platform Admin", is_default=False))
        meridian_viewer = User(organization_id=organizations[1].id, active_organization_id=organizations[1].id, email="meridian.viewer@catalogforge.demo", name="Meridian Readonly", role="Viewer", password_hash=password_hash("DemoPass123!"))
        db.add(meridian_viewer)
        db.flush()
        db.add(WorkspaceMembership(user_id=meridian_viewer.id, organization_id=organizations[1].id, role="Viewer", is_default=True))
        db.flush()

        all_vendors: dict[str, list[Vendor]] = {}
        all_categories: dict[str, list[Category]] = {}
        all_destinations: dict[str, list[PublicationDestination]] = {}
        for org_index, org in enumerate(organizations):
            vendors: list[Vendor] = []
            for ix, base_name in enumerate(VENDOR_NAMES):
                name = base_name if org_index == 0 else f"{base_name} · {org.name.split()[0]}"
                vendor = Vendor(organization_id=org.id, name=name, code=f"{org_index + 1}VND-{ix + 1:03d}", contact_email=f"ops+{org_index + 1}-{ix + 1}@synthetic.catalogforge.demo", sla_hours=24 + ix * 4, template_name=f"{base_name} mapping v{1 + ix % 2}", quality_score=round(0.67 + ((ix * 7 + org_index * 5) % 28) / 100, 2), source_freshness_days=1 + ix)
                db.add(vendor)
                db.flush()
                vendors.append(vendor)
                db.add(VendorTemplate(vendor_id=vendor.id, name=f"{base_name} mapping v1", version=1, status="Approved", mappings={"vendor_sku": "sku", "item_name": "title", "retail": "price", "stock": "inventory"}, confidence_threshold=0.80, approved_by="taxonomy@catalogforge.demo"))
                db.add(VendorTemplate(vendor_id=vendor.id, name=f"{base_name} mapping v2", version=2, status="Needs review" if ix % 3 == 0 else "Approved", mappings={"vendor_sku": "sku", "item_name": "title", "retail": "price", "shipping_mass": "weight"}, confidence_threshold=0.84, approved_by="admin@catalogforge.demo" if ix % 3 else None))
                db.add(VendorIntakeLink(organization_id=org.id, vendor_id=vendor.id, token=secrets.token_urlsafe(18), expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30 + ix), allowed_source_types={"types": ["CSV", "XLSX", "PDF", "JSON", "Image"]}, template_version="v2", status="Active"))
            all_vendors[org.id] = vendors
            categories: list[Category] = []
            for cat in CATEGORIES:
                category = Category(organization_id=org.id, name=cat.split(" / ")[-1], path=cat, required_attributes={"title": True, "sku": True, "image": True, "price": True}, version=1 + org_index, owner="taxonomy@catalogforge.demo")
                db.add(category)
                db.flush()
                categories.append(category)
                db.add_all([
                    AttributeDefinition(category_id=category.id, name="material", required=True, data_type="text", channel_applicability={"shopify": True}),
                    AttributeDefinition(category_id=category.id, name="color", required=False, data_type="text", channel_applicability={"shopify": True}),
                    AttributeDefinition(category_id=category.id, name="weight", required=True, data_type="measurement", unit_type="kg", channel_applicability={"shopify": True}),
                ])
            all_categories[org.id] = categories
            for rule_name, field, rule_type, severity, blocking, config in [
                ("SKU required", "sku", "required", "Blocking", True, {}),
                ("Price anomaly", "price", "relative_range", "Warning", False, {"median_multiplier": 3.5}),
                ("Image quality", "image", "quality_score", "Warning", False, {"min": 0.75}),
                ("Restricted words", "title", "contains_any", "Warning", False, {"words": ["best", "guaranteed"]}),
                ("Shopify shipping weight", "weight", "destination_required", "Blocking", True, {"destination": "Shopify"}),
            ]:
                db.add(ValidationRule(organization_id=org.id, name=rule_name, field_name=field, rule_type=rule_type, config=config, severity=severity, blocking=blocking, approval_state="Approved", applies_to={"destinations": ["Shopify"] if "Shopify" in rule_name else []}))
            destination_specs = [
                ("Shopify • Mock Store", "shopify_mock", "Demo connected", {"mock": True, "field_mapping": {"title": "title", "sku": "sku", "price": "variants.price", "weight": "variants.weight"}, "store": "catalogforge-demo.myshopify.com"}),
                ("WooCommerce • Mock Store", "woocommerce_mock", "Demo connected", {"mock": True}),
                ("PIM Export • CSV", "csv", "Demo connected", {"mock": True}),
                ("ERP • Configuration Boundary", "erp_boundary", "Not configured", {"mock": False, "configured": False}),
                ("Generic Webhook • Mock", "webhook_mock", "Demo connected", {"mock": True}),
            ]
            destinations: list[PublicationDestination] = []
            for name, destination_type, status, config in destination_specs:
                destination = PublicationDestination(organization_id=org.id, name=name, destination_type=destination_type, config=config, status=status, mapping_version=2 if org_index == 0 else 1, required_fields={"required": ["title", "sku", "price", "weight"] if destination_type == "shopify_mock" else ["title", "sku"]}, owner="publishing@catalogforge.demo")
                db.add(destination)
                db.flush()
                destinations.append(destination)
            all_destinations[org.id] = destinations

        files_by_org = [files[:24], files[24:39], files[39:]]
        products_by_org: dict[str, list[ProductCandidate]] = {}
        product_counts = [330, 110, 100]
        duplicate_targets = [45, 16, 14]
        for org_index, org in enumerate(organizations):
            vendors = all_vendors[org.id]
            categories = all_categories[org.id]
            destinations = all_destinations[org.id]
            jobs: list[UploadJob] = []
            for ix, (filename, _vendor_name, source_type) in enumerate(files_by_org[org_index]):
                vendor = vendors[ix % len(vendors)]
                # First Northstar job drives the guided demo scenario.
                status_cycle = ["Received", "Processing", "Extracted", "Needs review", "Blocked", "Approved", "Publishing", "Published", "Failed"]
                status = "Needs review" if org_index == 0 and ix == 0 else status_cycle[(ix + org_index) % len(status_cycle)]
                count = 72 if org_index == 0 and ix == 0 else 6 + ((ix + org_index * 7) * 7) % 26
                job = UploadJob(organization_id=org.id, vendor_id=vendor.id, filename=filename, source_type=source_type, status=status, product_count=count, confidence=round(0.72 + ((ix + org_index * 3) % 25) / 100, 2), validation_failures=5 if org_index == 0 and ix == 0 else ix % 6, reviewer_name=["Avery Chen", "Maya Torres", "Unassigned"][ix % 3], destination=["Shopify mock", "WooCommerce mock", "PIM export"][ix % 3], created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=(ix + org_index * 20) * 3), mode="Extract and review" if ix % 3 else "Validate only")
                db.add(job)
                db.flush()
                jobs.append(job)
                path = DOCS / filename
                source = SourceDocument(organization_id=org.id, upload_job_id=job.id, storage_key=f"demo_data/source_documents/{filename}", original_filename=filename, mime_type="application/pdf" if filename.endswith(".pdf") else "text/csv" if filename.endswith(".csv") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if filename.endswith(".xlsx") else "image/svg+xml", file_size=path.stat().st_size, source_type=source_type, page_count=2 if filename.endswith(".pdf") else 1, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), source_metadata={"synthetic": True, "detected_type": source_type, "ingestion": "seed"})
                db.add(source)
                db.flush()
                for page_no in range(1, source.page_count + 1):
                    page = SourcePage(source_document_id=source.id, page_number=page_no, preview_url=f"/demo_data/source_documents/{filename}", sheet_name="Catalog" if filename.endswith(".xlsx") else None)
                    db.add(page)
                    db.flush()
                    db.add(OCRBlock(source_page_id=page.id, text=f"SYNTHETIC source evidence from {filename}; page {page_no}", bbox={"x": 48, "y": 72, "w": 480, "h": 22}, confidence=0.98, method="deterministic_local_parser"))
                extraction = ExtractionJob(upload_job_id=job.id, provider="deterministic_local", status="completed", output_summary={"source_type": source_type, "candidates": count, "external_keys_used": False})
                db.add(extraction)
                durable = DurableJob(organization_id=org.id, job_type="Extraction", status="Needs review" if status == "Needs review" else "Completed", related_entity_type="upload_job", related_entity_id=job.id, source_record_id=source.id, idempotency_key=f"seed-extract-{org_index}-{ix}", retry_policy={"max_attempts": 3, "backoff": "linear"}, duration_ms=420 + ix * 11, output_artifacts={"candidates": count, "synthetic": True})
                db.add(durable)
                db.flush()
                db.add_all([JobEvent(durable_job_id=durable.id, state="Queued", message="Seeded job entered deterministic local queue."), JobEvent(durable_job_id=durable.id, state=durable.status, message="Deterministic source extraction completed or routed to review.")])
            db.flush()
            candidates: list[ProductCandidate] = []
            for i in range(product_counts[org_index]):
                job = jobs[i % len(jobs)]
                vendor = vendors[i % len(vendors)]
                title = f"{ADJECTIVES[i % 8]} {NOUNS[i % 8]} — {['Natural', 'Cloud', 'Parchment', 'Sage'][i % 4]}"
                sku = f"{vendor.code.replace('VND', 'CF')}-{org_index + 1}{i + 1001:04d}"
                missing = (org_index == 0 and i in {2, 75, 113, 200, 333}) or (org_index > 0 and i == 2)
                if missing:
                    sku = ""
                price = round(12 + (i % 63) * 3.7, 2)
                if org_index == 0 and i == 2:
                    price = 420.0
                status = "Approved" if i < int(product_counts[org_index] * 0.70) else ("Needs review" if i < int(product_counts[org_index] * 0.90) else "Blocked")
                attributes = {"material": ["Linen", "Oak", "Ceramic", "Seagrass", "Glass"][i % 5], "color": ["Natural", "Sage", "Cloud", "Ink"][i % 4], "dimensions": f"{20 + i % 20} × {10 + i % 13} cm", "weight": "" if missing else f"{0.2 + (i % 12) * 0.15:.2f} kg", "country_of_origin": "Synthetic"}
                candidate = ProductCandidate(organization_id=org.id, vendor_id=vendor.id, upload_job_id=job.id, title=title, sku=sku, vendor_sku=sku or f"VND-PENDING-{i}", brand=vendor.name, category=CATEGORIES[i % len(CATEGORIES)], product_type=CATEGORIES[i % len(CATEGORIES)].split(" / ")[-1], price=price, cost=round(price * 0.55, 2), currency="USD", inventory=(i * 7) % 160, barcode=f"890{org_index}{i % 10:01d}{i + 10101:08d}", image_url=f"/demo_data/product_images/product_{i % 60 + 1:02d}.svg", status=status, confidence=round(0.68 + (i % 30) / 100, 2), attributes=attributes, normalized={"sku": sku.replace(" ", "-").upper(), "taxonomy_confidence": round(0.8 + (i % 18) / 100, 2)})
                candidate.completeness_score = completeness_score(type("Candidate", (), {"title": candidate.title, "sku": candidate.sku, "category": candidate.category, "price": candidate.price, "attributes": candidate.attributes})())
                candidate.quality_score = round((candidate.completeness_score * 0.65) + (candidate.confidence * 35), 1)
                db.add(candidate)
                db.flush()
                candidates.append(candidate)
                if i < int(product_counts[org_index] * 0.70):
                    db.add(ProductRecord(product_candidate_id=candidate.id, version=1 + (i % 3), publication_status="Published" if i < 60 else "Approved"))
                db.add(ProductVersion(product_candidate_id=candidate.id, version=1, actor="system@catalogforge.demo", change_summary="Deterministic extraction created candidate.", before_json={}, after_json={"title": candidate.title, "sku": candidate.sku, "price": candidate.price}))
                if i < 75:
                    db.add(ProductImage(product_candidate_id=candidate.id, url=candidate.image_url, perceptual_hash=f"pHash-{i % 12:02d}", quality_score=round(0.78 + (i % 20) / 100, 2), alt_text=f"Synthetic {candidate.title}"))
                for fi, (field, val, confidence) in enumerate([("title", candidate.title, 0.97), ("sku", candidate.sku or "—", 0.72 if not candidate.sku else 0.94), ("price", f"{candidate.price:.2f}", 0.91), ("weight", candidate.attributes["weight"] or "—", 0.70 if not candidate.attributes["weight"] else 0.92)]):
                    db.add(ExtractedField(product_candidate_id=candidate.id, field_name=field, value=val, original_value=val, normalized_value=val.upper() if field == "sku" else val, confidence=confidence, evidence={"page": 1 + (i % 2), "sheet": "Catalog" if job.source_type == "Spreadsheet" else None, "row": 2 + i, "bbox": {"x": 72, "y": 138 + fi * 30, "w": 390, "h": 20}, "source_text": val, "document": job.filename}, extraction_method="deterministic_local_parser", validation_status="Needs review" if not candidate.sku else "Healthy", transformation_history={"steps": ["source parser", "field normalization"]}, destination_mapping={"Shopify": field}))
                if i % 4 == 0 or missing:
                    db.add(ReviewTask(organization_id=org.id, product_candidate_id=candidate.id, assignee=["Avery Chen", "Maya Torres", "Unassigned"][i % 3], priority="High" if i % 11 == 0 else "Normal", status="Open" if status != "Approved" else "Resolved", reason="Missing SKU" if not sku else "Confidence below auto-approval threshold", queue="Missing required fields" if not sku else "Low-confidence extraction", second_review=i % 19 == 0))
                if i < 110 or missing:
                    blocking = not bool(sku)
                    db.add(ValidationResult(product_candidate_id=candidate.id, rule_name="SKU required" if not sku else "Price anomaly", severity="error" if not sku else "warning", message="SKU is required before approval." if not sku else f"Price ${price:.2f} should be reviewed against vendor median.", state="open" if status != "Approved" else "resolved", blocking=blocking, remediation="Assign a normalized SKU." if not sku else "Confirm price in source evidence."))
                if i < 30:
                    db.add(AttributeValue(product_candidate_id=candidate.id, attribute_definition_id=categories[i % len(categories)].id, value=candidate.attributes["material"]))
                for destination in destinations[:3]:
                    blockers = []
                    if destination.destination_type == "shopify_mock" and not candidate.attributes["weight"]:
                        blockers.append("shipping weight")
                    if not candidate.sku:
                        blockers.append("SKU")
                    readiness = "Ready" if status == "Approved" and not blockers else "Blocked" if blockers else "Pending approval"
                    db.add(ChannelReadiness(organization_id=org.id, product_candidate_id=candidate.id, destination_id=destination.id, channel=destination.name, status=readiness, blockers={"items": blockers}, requirements=destination.required_fields))
            products_by_org[org.id] = candidates
            for i in range(duplicate_targets[org_index]):
                left = candidates[(i * 5) % len(candidates)]
                right = candidates[(i * 5 + 1) % len(candidates)]
                if org_index == 0 and i == 0:
                    left = candidates[0]
                    right = candidates[1]
                    right.title = left.title.replace("Natural", "Natural / 2-pack")
                group = DuplicateGroup(organization_id=org.id, similarity_score=round(0.76 + (i % 23) / 100, 2), rationale={"left_product_id": left.id, "right_product_id": right.id, "signals": {"normalized_sku": 0.0 if i else 0.92, "barcode": 0.0, "title": 0.94 if i == 0 else 0.81, "brand": 1.0, "category": 1.0, "attribute_overlap": 0.8, "image_embedding": 0.88}, "explanation": "High title, brand, category, attribute, and image similarity; human decision required.", "merge_impact": {"published_destinations": ["Shopify mock"] if i % 4 == 0 else [], "data_loss_warning": "Canonical record selection is required."}}, status="Candidate" if i < int(duplicate_targets[org_index] * 0.42) else "Not duplicate", risk_level="High" if i % 7 == 0 else "Medium", canonical_product_id=left.id if i % 3 else None, second_review_required=i % 7 == 0)
                db.add(group)
                db.flush()
                if group.status != "Candidate":
                    db.add(DuplicateDecision(duplicate_group_id=group.id, decision="keep_separate", rationale="Synthetic vendor pack-size variation", decided_by="Maya Torres", approval_state="Completed"))
            shop = destinations[0]
            for i in range(18 if org_index == 0 else 9):
                pub_status = "Completed" if i < 14 else "Failed"
                pub_job = PublicationJob(organization_id=org.id, destination_id=shop.id, status=pub_status, item_count=8 + i % 44, idempotency_key=f"seed-publish-{org_index + 1}-{i + 1:03d}", product_ids={"items": [p.id for p in candidates[i : i + 3]]}, mode="Publish", dry_run=False)
                db.add(pub_job)
                db.flush()
                db.add(PublicationAttempt(publication_job_id=pub_job.id, attempt_number=1 if i % 7 else 2, status=pub_status, error="Mock downstream throttle; retry available." if pub_status == "Failed" else None, response={"mock": True, "verified": pub_status == "Completed"}))
                db.add(SyncLog(publication_job_id=pub_job.id, message=f"Synthetic {pub_status.lower()} sync for {pub_job.item_count} products.", level="error" if pub_status == "Failed" else "info"))
            for i in range(6):
                product = candidates[i]
                db.add(ReconciliationIssue(organization_id=org.id, product_candidate_id=product.id, destination_id=shop.id, status="Open" if i < 3 else "Resolved", issue_type="mapping_mismatch" if i % 2 else "stale_destination_field", internal_snapshot={"title": product.title, "weight": product.attributes.get("weight")}, destination_snapshot={"title": product.title, "weight": ""}, resolution="Synthetic reconciliation is pending mapping correction." if i < 3 else "Mock retry reconciled destination state."))
            change_set = ChangeSet(organization_id=org.id, name=f"{org.name.split()[0]} July catalog approval batch", status="Needs review" if org_index == 0 else "Approved", created_by="catalog.ops@catalogforge.demo", risk_level="High" if org_index == 0 else "Medium", approval_policy={"required_role": "Publishing Manager", "second_review": True}, summary="Synthetic controlled release for approved product changes.")
            db.add(change_set)
            db.flush()
            for product in candidates[:6]:
                db.add(ChangeSetItem(change_set_id=change_set.id, product_candidate_id=product.id, entity_type="product", before_json={"status": "Needs review"}, after_json={"status": product.status}, validation_state="Healthy" if product.status == "Approved" else "Needs review"))
            db.add(ChangeApproval(change_set_id=change_set.id, approver="publishing@catalogforge.demo", role="Publishing Manager", decision="Approved" if org_index else "Pending", note="Synthetic policy-controlled release."))
            db.add(Report(organization_id=org.id, report_type="Vendor Quality Report", name=f"{org.name.split()[0]} vendor quality brief", status="Completed", generated_by="catalog.ops@catalogforge.demo", scope={"period": "30d", "synthetic": True}, data_freshness="Synthetic seed snapshot", export_id=f"RPT-{org_index + 1}-VQ-001"))
            db.add(ScheduledReport(organization_id=org.id, report_type="Executive Catalog Operations Brief", cadence="Weekly", delivery="in_app", status="Active"))
            db.add(Alert(organization_id=org.id, category="Vendor quality score drop", severity="High", title=f"{vendors[0].name} needs SKU remediation", message="Synthetic score declined because missing-SKU validation rate crossed the demo threshold.", status="Open", entity_type="vendor", entity_id=vendors[0].id, assigned_to="vendors@catalogforge.demo"))
            db.add(Alert(organization_id=org.id, category="Publish failure", severity="Medium", title="Mock destination requires retry", message="One or more simulated delivery attempts are retryable.", status="Acknowledged", entity_type="destination", entity_id=shop.id, assigned_to="publishing@catalogforge.demo"))
            db.add(Watchlist(organization_id=org.id, name="Products blocked for Shopify", filter_config={"destination": "Shopify", "status": "Blocked"}, owner="publishing@catalogforge.demo"))
            db.add_all([
                APIKey(organization_id=org.id, name="Demo ingestion key", key_prefix=f"cf_demo_{org_index + 1}_••••7P9A", secret_hash=hashlib.sha256(f"demo-key-{org_index}".encode()).hexdigest(), scopes={"scopes": ["intake.write", "documents.read"]}, expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=90)),
                WebhookDelivery(organization_id=org.id, event_type="publication.completed", endpoint="https://example.invalid/catalogforge/webhook", status_code=200, response_excerpt="Synthetic endpoint accepted event.", delivery_status="Delivered", retry_count=0, payload_preview={"synthetic": True, "product_count": 18}),
            ])
            for gate_key, label, status, severity, evidence, remediation in [
                ("tenant_isolation", "Backend-enforced organization isolation", "Passed", "Critical", {"tests": "cross-tenant product and document access denied"}, "Keep all new queries scoped by organization_id."),
                ("deterministic_local_mode", "No-key deterministic demo mode", "Passed", "Critical", {"requires_external_keys": False, "pipeline": "inline deterministic"}, "Do not introduce mandatory OCR, LLM, Redis, Postgres, or Docker dependency for local demo."),
                ("source_evidence", "Immutable source evidence and lineage", "Passed", "High", {"field_evidence_records": len(candidates[:8]) * 4}, "Continue preserving source pages, rows, OCR blocks, transformations, and reviewer overrides."),
                ("publishing_gate", "Validation and approval-gated publishing", "Passed", "Critical", {"mock_destination": shop.name, "idempotency": True}, "Do not mark sync success without connector verified success state."),
                ("governance_exports", "Audit and evidence export controls", "Passed", "High", {"reports": 1, "audit_events_seeded": 25}, "Audit every sensitive export and retention action."),
                ("provider_boundaries", "Optional provider and connector boundaries", "Passed", "Medium", {"ocr": "adapter boundary", "llm": "adapter boundary", "s3": "storage boundary"}, "Label external provider capabilities as optional and unverified in local demo."),
            ]:
                db.add(LaunchReadinessCheck(organization_id=org.id, gate_key=gate_key, label=label, status=status, severity=severity, evidence=evidence, remediation=remediation, last_checked_at=datetime.now(UTC).replace(tzinfo=None)))
            db.add_all([
                DataContract(organization_id=org.id, name="Shopify Mock Product Contract", contract_type="destination", version=3, status="Active", owner_role="Publishing Manager", schema_json={"required": ["title", "sku", "price", "weight"], "optional": ["barcode", "material", "color"]}, policy_json={"publish_blocking": True, "dry_run_supported": True, "mock_connector": True}, last_validated_at=datetime.now(UTC).replace(tzinfo=None)),
                DataContract(organization_id=org.id, name="Supplier CSV Intake Contract", contract_type="source", version=2, status="Active", owner_role="Catalog Operations Manager", schema_json={"accepted_columns": ["title", "sku", "brand", "category", "price", "inventory", "barcode"]}, policy_json={"checksum_required": True, "mapping_preview_required": True}, last_validated_at=datetime.now(UTC).replace(tzinfo=None)),
                SavedEntityView(organization_id=org.id, name="Launch blockers", entity_type="product", owner="catalog.ops@catalogforge.demo", filter_config={"validation": "blocking", "channel": "Shopify"}, column_config={"columns": ["title", "sku", "vendor", "blockers", "assignee"]}, is_shared=True),
                SavedEntityView(organization_id=org.id, name="Publishing release queue", entity_type="change_set", owner="publishing@catalogforge.demo", filter_config={"status": ["Needs review", "Approved"]}, column_config={"columns": ["name", "risk", "approvals", "destination"]}, is_shared=True),
            ])
            for i in range(25):
                product = candidates[i % len(candidates)]
                add_audit(db, org.id, "system@catalogforge.demo" if i % 2 else "catalog.ops@catalogforge.demo", ["document.extracted", "product.approved", "duplicate.separated", "publication.completed", "field.corrected", "change_set.created", "report.generated"][i % 7], ["upload_job", "product", "duplicate_group", "publication_job", "product", "change_set", "report"][i % 7], product.id, {"synthetic": True, "sequence": i + 1, "organization": org.slug})
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed(force=os.getenv("CATALOGFORGE_RESET_SYNTHETIC", "0") == "1")
    print("CatalogForge Phase 3 synthetic demo data seeded.")
