export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type ApiError = Error & { status?: number; detail?: string };

function workspaceHeader() {
  if (typeof window === "undefined") return {};
  const workspace = window.localStorage.getItem("catalogforge.workspace");
  return workspace ? { "X-CatalogForge-Workspace": workspace } : {};
}

function authHeader() {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("catalogforge.token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isForm && options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  Object.entries({ ...workspaceHeader(), ...authHeader() }).forEach(([key, value]) => headers.set(key, value));
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload?.detail || payload?.error?.message || `Request failed (${response.status})`) as ApiError;
    error.status = response.status;
    error.detail = payload?.detail;
    throw error;
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/csv") || contentType.includes("text/plain")) return (await response.text()) as T;
  return response.json() as Promise<T>;
}

export const client = {
  health: () => fetch(API_URL.replace(/\/api\/v1$/, "") + "/health").then((response) => response.json() as Promise<{ status: string; demo_mode: boolean }>),
  me: () => api<Me>("/auth/me"),
  login: (email: string, password: string) => api<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  switchWorkspace: (organizationId: string) => api<{ workspace: Workspace }>("/auth/switch-workspace", { method: "POST", body: JSON.stringify({ organization_id: organizationId }) }),
  overview: () => api<Overview>("/overview"),
  intakeJobs: () => api<ListResponse<IntakeJob>>("/intake/jobs"),
  intakeJob: (id: string) => api<IntakeJob>(`/intake/jobs/${id}`),
  processJob: (id: string, mapping?: Record<string, string>) => api(`/intake/jobs/${id}/process`, { method: "POST", body: JSON.stringify({ mapping: mapping || {} }) }),
  mappingPreview: (id: string) => api<MappingPreview>(`/intake/jobs/${id}/mapping-preview`),
  upload: (vendorId: string, file: File, mode = "Extract and review") => { const form = new FormData(); form.append("file", file); return api(`/intake/upload?vendor_id=${encodeURIComponent(vendorId)}&mode=${encodeURIComponent(mode)}`, { method: "POST", body: form }); },
  documents: () => api<ListResponse<Document>>('/documents'),
  document: (id: string) => api<Document>(`/documents/${id}`),
  documentEvidence: (id: string) => api<ListResponse<FieldEvidence>>(`/documents/${id}/evidence`),
  ocrBlocks: (id: string) => api<ListResponse<OcrBlock>>(`/documents/${id}/ocr-blocks`),
  products: (params = "") => api<ListResponse<Product>>(`/products${params ? `?${params}` : ""}`),
  product: (id: string) => api<Product>(`/products/${id}`),
  updateProduct: (id: string, payload: Partial<Product>) => api<Product>(`/products/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  approveProduct: (id: string, note = "") => api<Product>(`/products/${id}/approve`, { method: "POST", body: JSON.stringify({ note }) }),
  rejectProduct: (id: string, reason = "") => api(`/products/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  productReadiness: (id: string) => api<{ items: Readiness[] }>(`/products/${id}/channel-readiness`),
  reviewTasks: () => api<ListResponse<ReviewTask>>("/review/tasks"),
  addNote: (id: string, body: string) => api(`/review/products/${id}/note`, { method: "POST", body: JSON.stringify({ body }) }),
  requestClarification: (id: string) => api(`/review/products/${id}/request-clarification`, { method: "POST" }),
  duplicates: () => api<ListResponse<DuplicateGroup>>("/duplicates"),
  duplicate: (id: string) => api<DuplicateDetail>(`/duplicates/${id}`),
  mergeDuplicate: (id: string, payload: { rationale: string; canonical_product_id?: string; confirm_second_review?: boolean }) => api(`/duplicates/${id}/merge`, { method: "POST", body: JSON.stringify(payload) }),
  separateDuplicate: (id: string, rationale: string) => api(`/duplicates/${id}/separate`, { method: "POST", body: JSON.stringify({ rationale }) }),
  categories: () => api<ListResponse<Category>>("/taxonomy/categories"),
  attributes: () => api<ListResponse<Attribute>>("/taxonomy/attributes"),
  rules: () => api<ListResponse<Rule>>("/taxonomy/rules"),
  quality: () => api<Quality>("/quality/overview"),
  destinations: () => api<ListResponse<Destination>>("/publish/destinations"),
  publishJobs: () => api<ListResponse<PublishJob>>("/publish/jobs"),
  createPublish: (payload: { destination_id?: string; product_ids?: string[]; mode?: string; idempotency_key?: string; change_set_id?: string }) => api<PublishJob>("/publish/jobs", { method: "POST", body: JSON.stringify(payload) }),
  retryPublish: (id: string) => api(`/publish/jobs/${id}/retry`, { method: "POST" }),
  rollbackPublish: (id: string) => api(`/publish/jobs/${id}/rollback`, { method: "POST" }),
  reconcile: () => api(`/publish/reconcile`, { method: "POST" }),
  reconciliation: () => api<ListResponse<Reconciliation>>("/publish/reconciliation"),
  vendors: () => api<ListResponse<Vendor>>("/vendors"),
  vendor: (id: string) => api<VendorDetail>(`/vendors/${id}`),
  createIntakeLink: (id: string) => api(`/vendors/${id}/intake-links`, { method: "POST" }),
  changeSets: () => api<ListResponse<ChangeSet>>("/change-sets"),
  changeSet: (id: string) => api<ChangeSet>(`/change-sets/${id}`),
  createChangeSet: (payload: { name: string; product_ids: string[]; summary?: string; risk_level?: string }) => api<ChangeSet>("/change-sets", { method: "POST", body: JSON.stringify(payload) }),
  submitChangeSet: (id: string) => api(`/change-sets/${id}/submit`, { method: "POST" }),
  approveChangeSet: (id: string, decision: string) => api(`/change-sets/${id}/approve`, { method: "POST", body: JSON.stringify({ decision }) }),
  lineage: (id: string) => api<Lineage>(`/lineage/products/${id}`),
  evidencePackage: (id: string) => api(`/lineage/products/${id}/evidence-package`),
  reports: () => api<Reports>("/reports"),
  createReport: (payload: { report_type: string; name?: string }) => api<Report>("/reports", { method: "POST", body: JSON.stringify(payload) }),
  scheduleReport: (payload: { report_type: string; cadence?: string }) => api(`/reports/schedules`, { method: "POST", body: JSON.stringify(payload) }),
  alerts: () => api<Alerts>("/alerts"),
  alertAction: (id: string, action: string) => api(`/alerts/${id}/action`, { method: "POST", body: JSON.stringify({ action }) }),
  assistant: (question: string, mode = "Executive Operations Brief") => api<AssistantAnswer>("/assistant/query", { method: "POST", body: JSON.stringify({ question, mode }) }),
  audit: () => api<ListResponse<Audit>>("/governance/audit-events"),
  apiKeys: () => api<ListResponse<ApiKey>>("/governance/api-keys"),
  createApiKey: (name: string) => api(`/governance/api-keys`, { method: "POST", body: JSON.stringify({ name, scopes: ["documents.read", "intake.write"] }) }),
  revokeApiKey: (id: string) => api(`/governance/api-keys/${id}/revoke`, { method: "POST" }),
  webhooks: () => api<ListResponse<Webhook>>("/governance/webhooks"),
  settings: () => api<Settings>("/governance/settings"),
  rolesUsers: () => api<{ roles: Role[]; users: User[] }>("/governance/roles-users"),
  pipeline: () => api<Pipeline>("/pipeline/jobs"),
  retryPipeline: (id: string) => api(`/pipeline/jobs/${id}/retry`, { method: "POST" }),
  operations: () => api<Operations>("/platform/operations"),
  launchReadiness: () => api<LaunchReadiness>("/launch/readiness"),
  goldenDemo: () => api<GoldenDemo>("/launch/golden-demo"),
  dataContracts: () => api<ListResponse<DataContract>>("/launch/data-contracts"),
  savedViews: () => api<ListResponse<SavedView>>("/launch/saved-views"),
  permissionMatrix: () => api<PermissionMatrix>("/governance/permission-matrix"),
  auditExport: () => api<string>("/governance/audit-export"),
  productReleaseGate: (id: string) => api<ProductReleaseGate>(`/products/${id}/release-gate`),
  deliveryProof: (id: string) => api<DeliveryProof>(`/publish/jobs/${id}/delivery-proof`),
  search: (q: string) => api<ListResponse<SearchItem>>(`/search?q=${encodeURIComponent(q)}`),
};

export type Workspace = { id: string; name: string; slug: string; role?: string; synthetic?: boolean };
export type Me = { id: string; email: string; name: string; role: string; workspace: Workspace; workspaces: Workspace[] };
export type LoginResponse = { access_token: string; user: { id: string; email: string; name: string; role: string }; workspace: Workspace; workspaces: Workspace[] };
export type ListResponse<T> = { items: T[]; total?: number };
export type Overview = { metrics: Record<string, number>; confidence_distribution: { band: string; count: number }[]; quality_trend: { day: string; score: number }[]; recent_activity: IntakeJob[]; summary: string; limitations: string };
export type IntakeJob = { id: string; filename: string; vendor: string; vendor_id: string; source_type: string; status: string; product_count: number; confidence: number; validation_failures: number; reviewer: string; destination: string; document_id?: string; created_at: string; mode?: string; source_quality_score?: number; durable_job?: { id: string; status: string } };
export type Document = { id: string; upload_job_id: string; filename: string; mime_type: string; file_size: number; source_type: string; page_count: number; sha256: string; retention_state: string; duplicate_of_id?: string; source_metadata: Record<string, unknown>; pages: { id: string; page_number: number; sheet_name?: string; preview_url: string }[] };
export type FieldEvidence = { id: string; product_id: string; field: string; value: string; original_value: string; normalized_value: string; confidence: number; evidence: Record<string, unknown>; method: string; validation_status: string; reviewer_override: boolean; transformation_history: Record<string, unknown>; destination_mapping: Record<string, unknown> };
export type OcrBlock = { id: string; text: string; bbox: Record<string, number>; confidence: number; method: string; page_id: string };
export type Product = { id: string; title: string; sku: string; vendor_sku?: string; brand: string; category: string; product_type?: string; price: number; cost?: number; currency?: string; inventory: number; barcode: string; image_url: string; status: string; confidence: number; completeness_score: number; quality_score: number; attributes: Record<string, string>; validations: { id: string; rule: string; severity: string; message: string; state: string; blocking: boolean; remediation: string }[]; evidence?: FieldEvidence[]; versions?: { version: number; actor: string; summary: string; at: string }[]; comments?: { id: string; author: string; body: string; at: string }[]; channel_readiness?: Readiness[] };
export type Readiness = { id: string; channel: string; status: string; blockers: { items?: string[] }; requirements: Record<string, unknown> };
export type ReviewTask = { id: string; product_id: string; product: Product; assignee: string; priority: string; status: string; reason: string; queue: string; locked_by?: string; second_review: boolean; created_at: string };
export type DuplicateGroup = { id: string; similarity_score: number; status: string; risk_level: string; second_review_required: boolean; canonical_product_id?: string; rationale: Record<string, unknown> };
export type DuplicateDetail = DuplicateGroup & { left?: Product; right?: Product; decisions: { id: string; decision: string; rationale: string; decided_by: string; approval_state: string; at: string }[] };
export type Category = { id: string; name: string; path: string; version: number; owner: string; status: string; required_attributes: Record<string, boolean> };
export type Attribute = { id: string; category: string; name: string; required: boolean; data_type: string; unit_type?: string; status: string; channel_applicability: Record<string, boolean> };
export type Rule = { id: string; name: string; field_name: string; rule_type: string; severity: string; blocking: boolean; approval_state: string; config: Record<string, unknown> };
export type Quality = { overall_catalog_quality_score: number; completeness_score: number; validation_failure_rate: number; duplicate_risk_rate: number; channel_readiness_records: number; blocked_products: number; common_failures: { rule: string; count: number }[]; insight: string; limitations: string };
export type Destination = { id: string; name: string; type: string; status: string; mapping_version: number; required_fields: { required?: string[] }; config: Record<string, unknown>; failure_count: number; owner: string };
export type PublishJob = { id: string; status: string; item_count: number; idempotency_key: string; destination_id?: string; destination?: string; product_ids?: { items?: string[] }; mode?: string; dry_run?: boolean; change_set_id?: string; created_at?: string };
export type Reconciliation = { id: string; product_id: string; destination_id: string; status: string; issue_type: string; internal: Record<string, unknown>; destination: Record<string, unknown>; resolution: string };
export type Vendor = { id: string; name: string; code: string; files: number; catalog_volume: number; confidence: number; quality_score: number; validation_failure_rate: number; source_freshness_days: number; frequent_issue: string; template: string; status: string };
export type VendorDetail = Vendor & { jobs: IntakeJob[]; templates: { id: string; name: string; version: number; status: string; mappings: Record<string, string>; confidence_threshold: number }[]; intake_links: { id: string; token_preview: string; expires_at: string; status: string }[] };
export type ChangeSet = { id: string; name: string; status: string; risk_level: string; created_by: string; summary: string; approval_policy: Record<string, unknown>; created_at?: string; items?: { id: string; product_id?: string; entity_type: string; before: Record<string, unknown>; after: Record<string, unknown>; validation_state: string }[]; approvals?: { id: string; approver: string; role: string; decision: string; note: string; at: string }[] };
export type Lineage = { product_id: string; nodes: { id: string; type: string; label: string; metadata?: Record<string, unknown> }[]; edges: { from: string; to: string; label: string }[]; field_lineage: unknown[] };
export type Report = { id: string; type?: string; report_type?: string; name: string; status: string; export_id: string; artifact_path?: string; created_at?: string };
export type Reports = { items: Report[]; scheduled: { id: string; type: string; cadence: string; delivery: string; status: string }[] };
export type Alerts = { items: { id: string; category: string; severity: string; title: string; message: string; status: string; entity_type: string; entity_id: string; assigned_to?: string; created_at: string }[]; watchlists: { id: string; name: string }[] };
export type AssistantAnswer = { executive_summary: string; scope: Record<string, unknown>; data_sources: string[]; supporting_metrics: Record<string, number>; evidence_links: Record<string, unknown[]>; data_quality_caveats: string; confidence: string; limitations: string; suggested_next_action: string; mode: string };
export type Audit = { id: string; at: string; actor: string; action: string; entity_type: string; entity_id: string; payload: Record<string, unknown> };
export type ApiKey = { id: string; name: string; prefix: string; scopes: { scopes: string[] }; expires_at?: string; revoked_at?: string; last_used_at?: string };
export type Webhook = { id: string; event_type: string; endpoint: string; status_code: number; response_excerpt: string; delivery_status: string; retry_count: number };
export type Settings = { workspace: string; workspace_id: string; retention_days: number; demo_mode: boolean; security_wording: string; legal_hold: string };
export type Role = { id: string; name: string; permissions: Record<string, boolean> };
export type User = { id: string; name: string; email: string; role: string };
export type Pipeline = { items: { id: string; type: string; status: string; related_entity_type: string; related_entity_id: string; retry_count: number; error_reason?: string; worker: string; duration_ms?: number; created_at: string }[]; queue_health: { inline_mode: boolean; failed: number; waiting_for_review: number } };
export type Operations = { health: Record<string, string>; telemetry: Record<string, number>; disclaimer: string };
export type MappingPreview = { document_id: string; columns: string[]; rows: Record<string, unknown>[]; suggested_mapping: Record<string, string>; mode: string };
export type SearchItem = { type: string; id: string; label: string; metadata: string; href: string };

export type LaunchReadiness = { phase: string; workspace_id: string; launch_score: number; status: string; disclaimer: string; checks: { key: string; label: string; status: string; severity: string; evidence: Record<string, unknown>; remediation: string; last_checked_at: string }[]; claims_policy: Record<string, boolean> };
export type GoldenDemo = { title: string; synthetic: boolean; steps: { step: number; label: string; entity_type: string; entity_id?: string | null; href: string }[]; operator_notes: string };
export type DataContract = { id: string; name: string; type: string; version: number; status: string; owner_role: string; schema: Record<string, unknown>; policy: Record<string, unknown>; last_validated_at?: string | null };
export type SavedView = { id: string; name: string; entity_type: string; owner: string; filters: Record<string, unknown>; columns: Record<string, unknown>; shared: boolean };
export type PermissionMatrix = { items: { role: string; rank: number; permissions: Record<string, boolean> }[]; enforcement: string };
export type ProductReleaseGate = { product_id: string; title: string; status: string; approved_for_internal_catalog: boolean; publish_blockers: string[]; destination_readiness: { channel: string; status: string; blockers: { items?: string[] } }[]; policy: string };
export type DeliveryProof = { publication_job_id: string; destination: string; mock_connector: boolean; verified_delivery: boolean; job_status: string; idempotency_key: string; attempts: { attempt: number; status: string; error?: string; response: Record<string, unknown> }[]; logs: { level: string; message: string; at: string }[]; claim_boundary: string };
