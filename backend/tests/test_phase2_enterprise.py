import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_catalogforge.db"

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app

client = TestClient(app)
API = "/api/v1"


def login(email: str = "admin@catalogforge.demo") -> tuple[dict[str, str], dict]:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "DemoPass123!"})
    assert response.status_code == 200, response.text
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload


def active_vendor(headers: dict[str, str]) -> str:
    response = client.get(f"{API}/vendors", headers=headers)
    assert response.status_code == 200
    return response.json()["items"][0]["id"]


def upload_and_process(headers: dict[str, str], filename: str, data: bytes, mime: str) -> dict:
    response = client.post(
        f"{API}/intake/upload?vendor_id={active_vendor(headers)}&mode=Extract%20and%20review",
        headers=headers,
        files={"file": (filename, data, mime)},
    )
    assert response.status_code == 200, response.text
    upload = response.json()
    preview = client.get(f"{API}/intake/jobs/{upload['job_id']}/mapping-preview", headers=headers)
    assert preview.status_code == 200
    processed = client.post(f"{API}/intake/jobs/{upload['job_id']}/process", headers=headers, json={})
    assert processed.status_code == 200, processed.text
    assert processed.json()["external_keys_used"] is False
    return {**upload, **processed.json(), "preview": preview.json()}


def test_tenant_isolation_and_workspace_switch():
    headers, login_payload = login()
    north_products = client.get(f"{API}/products?limit=1", headers=headers)
    assert north_products.status_code == 200
    north_product_id = north_products.json()["items"][0]["id"]
    meridian = next(item for item in login_payload["workspaces"] if item["slug"] == "meridian-marketplace")
    switched = client.post(f"{API}/auth/switch-workspace", headers=headers, json={"organization_id": meridian["id"]})
    assert switched.status_code == 200
    meridian_headers = {**headers, "X-CatalogForge-Workspace": meridian["id"]}
    cross_tenant = client.get(f"{API}/products/{north_product_id}", headers=meridian_headers)
    assert cross_tenant.status_code == 404
    assert client.get(f"{API}/products", headers=meridian_headers).json()["total"] != north_products.json()["total"]


def test_viewer_role_cannot_manage_api_keys_or_switch_unassigned_workspace():
    headers, _ = login("viewer@catalogforge.demo")
    denied = client.post(f"{API}/governance/api-keys", headers=headers, json={"name": "should fail", "scopes": ["intake.write"]})
    assert denied.status_code == 403
    meridian = client.post(f"{API}/auth/switch-workspace", headers=headers, json={"organization_id": "meridian-marketplace"})
    assert meridian.status_code == 403


def test_real_csv_import_column_mapping_evidence_and_audit():
    headers, _ = login()
    csv = b"title,sku,brand,price,inventory,barcode,weight\nField Lamp,,Luma,49.99,7,901234567890,0.70 kg\n"
    result = upload_and_process(headers, "phase2_field_lamp.csv", csv, "text/csv")
    assert result["source_type"] == "CSV"
    assert result["product_count"] == 1
    assert result["preview"]["suggested_mapping"]["title"] == "title"
    evidence = client.get(f"{API}/documents/{result['document_id']}/evidence", headers=headers)
    assert evidence.status_code == 200
    values = evidence.json()["items"]
    assert any(item["field"] == "title" and item["evidence"]["row"] == 2 for item in values)
    audits = client.get(f"{API}/governance/audit-events", headers=headers).json()["items"]
    assert any(item["action"] == "intake.processed" for item in audits)


def test_real_xlsx_import_and_deterministic_extraction():
    headers, _ = login()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"
    sheet.append(["title", "sku", "brand", "price", "inventory", "barcode", "weight"])
    sheet.append(["XLSX Kettle", "XLSX-001", "Forge Home", 39.99, 12, "789012345678", "1.2 kg"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    result = upload_and_process(headers, "phase2_kettle.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert result["source_type"] == "XLSX"
    assert result["product_count"] == 1
    assert result["preview"]["rows"][0]["title"] == "XLSX Kettle"


def test_product_review_correction_versions_approval_and_readiness():
    headers, _ = login()
    upload_and_process(headers, "review_product.csv", b"title,sku,brand,price,inventory,barcode,weight\nReview Kettle,,Luma,31.50,5,234567890123,0.8 kg\n", "text/csv")
    products = client.get(f"{API}/products?q=Review%20Kettle", headers=headers)
    product_id = products.json()["items"][0]["id"]
    corrected = client.patch(f"{API}/products/{product_id}", headers=headers, json={"sku": "REV-0001", "attributes": {"weight": "0.8 kg"}})
    assert corrected.status_code == 200
    versions = client.get(f"{API}/products/{product_id}/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()["items"]) >= 1
    approved = client.post(f"{API}/products/{product_id}/approve", headers=headers, json={"note": "Reviewed with source evidence."})
    assert approved.status_code == 200
    readiness = client.get(f"{API}/products/{product_id}/channel-readiness", headers=headers)
    assert readiness.status_code == 200
    assert any(item["channel"].startswith("Shopify") for item in readiness.json()["items"])


def test_duplicate_governance_second_review_and_immutable_history():
    headers, _ = login()
    groups = client.get(f"{API}/duplicates?status=Candidate", headers=headers)
    assert groups.status_code == 200
    group_id = groups.json()["items"][0]["id"]
    detail = client.get(f"{API}/duplicates/{group_id}", headers=headers).json()
    first = client.post(f"{API}/duplicates/{group_id}/merge", headers=headers, json={"rationale": "Evidence-backed merge test", "canonical_product_id": detail["left"]["id"], "confirm_second_review": False})
    assert first.status_code == 200
    assert first.json()["status"] in {"In review", "Merged"}
    if first.json()["status"] == "In review":
        second = client.post(f"{API}/duplicates/{group_id}/merge", headers=headers, json={"rationale": "Second reviewer confirms merge impact.", "canonical_product_id": detail["left"]["id"], "confirm_second_review": True})
        assert second.status_code == 200
        assert second.json()["status"] == "Merged"
    history = client.get(f"{API}/duplicates/{group_id}/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()["items"]) >= 1


def test_change_set_publish_idempotency_retry_reconciliation_and_report():
    headers, _ = login()
    product = client.get(f"{API}/products?status=Approved&limit=1", headers=headers).json()["items"][0]
    change = client.post(f"{API}/change-sets", headers=headers, json={"name": "Phase 2 publish gate", "product_ids": [product["id"]], "summary": "Test governed publication", "risk_level": "Medium"})
    assert change.status_code == 200
    change_id = change.json()["id"]
    assert client.post(f"{API}/change-sets/{change_id}/submit", headers=headers).status_code == 200
    approved_change = client.post(f"{API}/change-sets/{change_id}/approve", headers=headers, json={"decision": "Approved", "note": "Approved by test org admin"})
    assert approved_change.status_code == 200
    destination = client.get(f"{API}/publish/destinations", headers=headers).json()["items"][0]
    payload = {"destination_id": destination["id"], "product_ids": [product["id"]], "mode": "Dry run", "idempotency_key": "phase2-publish-idempotency", "change_set_id": change_id}
    first = client.post(f"{API}/publish/jobs", headers=headers, json=payload)
    second = client.post(f"{API}/publish/jobs", headers=headers, json=payload)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    retry = client.post(f"{API}/publish/jobs/{first.json()['id']}/retry", headers=headers)
    assert retry.status_code == 200
    rollback = client.post(f"{API}/publish/jobs/{first.json()['id']}/rollback", headers=headers)
    assert rollback.status_code == 200
    reconcile = client.post(f"{API}/publish/reconcile", headers=headers)
    assert reconcile.status_code == 200
    report = client.post(f"{API}/reports", headers=headers, json={"report_type": "Vendor Quality Report", "name": "Phase 2 verification report"})
    assert report.status_code == 200
    artifact = client.get(f"{API}/reports/{report.json()['id']}/export", headers=headers)
    assert artifact.status_code == 200
    assert artifact.headers["content-type"].startswith("application/pdf")


def test_security_headers_pipeline_and_governed_assistant():
    headers, _ = login()
    health = client.get("/health")
    assert health.headers["x-content-type-options"] == "nosniff"
    overview = client.get(f"{API}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["metrics"]["products_extracted"] > 0
    pipeline = client.get(f"{API}/pipeline/jobs", headers=headers)
    assert pipeline.status_code == 200
    assert pipeline.json()["queue_health"]["inline_mode"] is True
    answer = client.post(f"{API}/assistant/query", headers=headers, json={"question": "Which vendors are causing the most validation failures?", "mode": "Vendor Quality Mode"})
    assert answer.status_code == 200
    assert answer.json()["data_sources"]
    unsupported = client.post(f"{API}/assistant/query", headers=headers, json={"question": "What are last quarter marketplace sales?", "mode": "Executive Operations Brief"})
    assert unsupported.status_code == 200
    assert "cannot verify" in unsupported.json()["limitations"].lower()


def test_phase3_launch_readiness_permission_matrix_and_contracts():
    headers, _ = login()
    readiness = client.get(f"{API}/launch/readiness", headers=headers)
    assert readiness.status_code == 200, readiness.text
    payload = readiness.json()
    assert payload["launch_score"] >= 90
    assert any(item["key"] == "publishing_gate" and item["status"] == "Passed" for item in payload["checks"])
    contracts = client.get(f"{API}/launch/data-contracts", headers=headers)
    assert contracts.status_code == 200
    assert any(item["name"] == "Shopify Mock Product Contract" for item in contracts.json()["items"])
    matrix = client.get(f"{API}/governance/permission-matrix", headers=headers)
    assert matrix.status_code == 200
    assert "Server-side" in matrix.json()["enforcement"]


def test_phase3_product_release_gate_delivery_proof_and_audit_export():
    headers, _ = login()
    product = client.get(f"{API}/products?limit=1", headers=headers).json()["items"][0]
    gate = client.get(f"{API}/products/{product['id']}/release-gate", headers=headers)
    assert gate.status_code == 200
    assert "policy" in gate.json()
    job = client.get(f"{API}/publish/jobs", headers=headers).json()["items"][0]
    proof = client.get(f"{API}/publish/jobs/{job['id']}/delivery-proof", headers=headers)
    assert proof.status_code == 200
    assert proof.json()["mock_connector"] is True
    export = client.get(f"{API}/governance/audit-export", headers=headers)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "payload_redacted" in export.text


def test_phase3_api_key_authentication_boundary_and_golden_demo():
    headers, _ = login()
    created = client.post(f"{API}/governance/api-keys", headers=headers, json={"name": "Phase 3 scoped key", "scopes": ["documents.read", "intake.write"]})
    assert created.status_code == 200, created.text
    key = created.json()["key"]
    api_response = client.get(f"{API}/launch/saved-views", headers={"X-CatalogForge-API-Key": key})
    assert api_response.status_code == 200, api_response.text
    golden = client.get(f"{API}/launch/golden-demo", headers=headers)
    assert golden.status_code == 200
    assert len(golden.json()["steps"]) >= 7
