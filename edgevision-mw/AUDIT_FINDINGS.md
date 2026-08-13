# Deep Audit Findings — EdgeVision-MW Control Plane

**Audit Date:** 2026-07-26
**Scope:** Logic correctness, compliance, reliability, reusability, operability
**Baseline:** AGENTS.md 34-item known-issues list

---

## CRITICAL — Data Integrity / Financial Loss / Compliance Violation

### C1. No Refund Path for Failed/Blocked Exports (Financial Loss)
**AGENTS.md gap:** Not listed
**File:** `app/services/billing.py:49` (deduction), `app/services/compliance.py:143` (blocking)
**Impact:** Buyer permanently loses credit when export fails or is blocked by consent withdrawal.
- Credit is deducted at initiation (`billing.py:49`)
- Celery retries exhaust → export stuck in PENDING/PROCESSING → no credit refund
- Consent withdrawal blocks export (`compliance.py:143`) → no credit refund
- `FAILED` status is never assigned — export is permanently stuck
- **No `refund_escrow()` function exists anywhere in the codebase**

### C2. `confirm_delivery` Has No Status Guard (Compliance Bypass)
**AGENTS.md gap:** Not listed
**File:** `app/services/billing.py:131-138`
**Impact:** Compliance enforcement can be bypassed.
- `confirm_delivery` unconditionally sets `ExportStatus.COMPLETED` (line 136)
- A `BLOCKED` export (blocked due to consent withdrawal) can be resurrected to `COMPLETED`
- A `PENDING` export (never processed) can be faked as `COMPLETED`
- No `SELECT FOR UPDATE` → race condition with Celery `_export_async`

### C3. QA Review Has No Self-Assignment Protection (Certification Bypass)
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:132-174`
**Impact:** A QA reviewer can certify their own annotation, defeating quality assurance.
- No check that `annotator_id != reviewer_id`
- If reviewer reviews own work → labels identical → IoU=1.0 → IAA=1.0 ≥ 0.96 → guaranteed CERTIFIED
- This is a **certification bypass** — zero quality assurance when reviewer is original annotator

### C4. `submit_labels` Missing Status Guard (State Machine Violation)
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:105-118`
**Impact:** Labels can be submitted on annotations in any status (PENDING, QA_REVIEW, CERTIFIED, REJECTED).
- No check that `annotation.status == AnnotationStatus.HUMAN_REVIEW`
- Status is unconditionally overwritten to QA_REVIEW
- Could corrupt already-certified or rejected annotations

### C5. `submit_review` Missing Status Guard (State Machine Violation)
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:139-163`
**Impact:** QA reviews can be submitted on annotations in any status.
- No check that `annotation.status == AnnotationStatus.QA_REVIEW`
- Could overwrite PENDING, HUMAN_REVIEW, CERTIFIED, or REJECTED annotations

### C6. All Monetary Values Use `float` Instead of `Decimal` (Financial Precision)
**AGENTS.md gap:** Not listed
**File:** `app/models/buyer.py:51`, `app/models/dataset.py:50`, `app/models/quote.py:21-24`, all billing/catalog calculations
**Impact:** IEEE 754 floating-point rounding errors in all financial operations.
- `User.credit_balance_usd`: `Mapped[float]` with DB `Numeric(12,2)` — precision undermined at Python layer
- `Export.price_usd`: same mismatch
- `Dataset.price_usd` and `Quote` prices: `Float` at both DB and Python layers — no precision guarantee
- Compound errors in revenue aggregation (`billing.py:185-195` loop)
- `0.1 + 0.2 ≠ 0.3` scenarios in credit comparison (`billing.py:43`)

### C7. Node Health Status Unconditionally Set to ONLINE (Fleet Blindness)
**AGENTS.md gap:** Not listed
**File:** `app/services/fleet.py:48-55`
**Impact:** Every heartbeat unconditionally sets `NodeStatus.ONLINE` regardless of telemetry.
- A node with 5% battery, 95°C CPU, full storage → still `ONLINE`
- `check_node_health_from_payload` generates alerts but has zero effect on status
- `DEGRADED`, `MAINTENANCE`, `OFFLINE` are all unreachable dead states
- No background task ever transitions nodes to OFFLINE even when heartbeats stop

### C8. Revenue Tracking Completely Broken (Dead State `SOLD`)
**AGENTS.md gap:** Not listed
**File:** `app/services/catalog.py` (absent), `app/services/billing.py:176-183`
**Impact:** `DatasetStatus.SOLD` and `Dataset.sold_at` are never populated.
- `get_revenue_breakdown` queries by `sold_at` date → always returns 0
- `total_revenue` metric is permanently broken
- No code path transitions dataset from READY to SOLD after export

---

## HIGH — Dead States / Broken Logic / Missing Features

### H1. `FAILED` Export Status Is Unreachable
**AGENTS.md gap:** Not listed
**File:** `app/workers/tasks.py:263-319`
**Impact:** When Celery retries exhaust, export stays stuck in PENDING/PROCESSING forever.
- `_export_async` raises → Celery retries 3× → exception propagates → export never transitions to FAILED
- Buyer's credit remains deducted with no refund (see C1)

### H2. `EXPIRED` Consent Status Is Unreachable
**AGENTS.md confirmed:** Issue #32 notes missing expiry background task
**File:** `app/services/compliance.py:174-216`
**Expanded:** Not just a missing background job — `verify_consent` checks expiry (`line 201`) but never transitions status to EXPIRED. Expired consents still appear as ACTIVE in the database.

### H3. `AUTO_LABELED` Annotation Status Is Unreachable
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:362-365`
**Impact:** `get_pending_jobs` queries for `AUTO_LABELED` annotations but nothing ever creates them.
- `auto_label_task` only transitions batch status, never creates/updates Annotation records
- The entire auto-label → human review handoff is disconnected

### H4. `FOR_SALE` Dataset Status Is Unreachable
**AGENTS.md gap:** Not listed
**File:** `app/services/catalog.py`
**Impact:** Datasets transition BUILDING → READY and are immediately available. No listing/publishing gate.

### H5. `PENDING` Batch Status Is Unreachable at Creation
**AGENTS.md gap:** Not listed
**File:** `app/services/ingestion.py:71`
**Impact:** Batches created with `VALIDATING` status, skipping PENDING. `get_queue_stats` shows `total_pending=0` permanently.

### H6. `REJECTED` Batch Status Is Unreachable
**AGENTS.md gap:** Not listed
**File:** `app/services/ingestion.py:47-59`
**Impact:** Checksum/file-size errors raise `ValueError` before batch record is created. No batch record with REJECTED status can exist.

### H7. `DEGRADED`/`MAINTENANCE`/`OFFLINE` Node Statuses Are All Unreachable
**AGENTS.md gap:** Not listed (partially covered by #14)
**File:** `app/services/fleet.py`
**Impact:** Only ONLINE is ever assigned. Fleet monitoring dashboard would show all nodes as healthy.

### H8. `VALIDATED` Batch Status Is a Transient Ghost State
**AGENTS.md gap:** Not listed
**File:** `app/workers/tasks.py:213-218`
**Impact:** Set and immediately overwritten to INGESTED within same function call. If second commit fails, batch is stuck permanently.

### H9. No Re-Assignment / Rework Cycle for Rejected Annotations
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py`
**Impact:** Rejected annotations are permanently stuck in REJECTED. No code path allows re-assignment for rework.

### H10. TOCTOU Race on Credit Check
**AGENTS.md gap:** Not listed
**File:** `app/services/billing.py:43-49`
**Impact:** Two concurrent `initiate_export` calls can both pass balance check and both deduct, pushing balance negative.
- No `SELECT FOR UPDATE` on user row
- Credit check and deduction are not atomic

### H11. Duplicate Schema Files (`consent.py` Is Dead Code)
**AGENTS.md gap:** Not listed
**File:** `app/schemas/consent.py` (8 models), vs `app/schemas/compliance.py` (7 models)
**Impact:** `consent.py` models are never imported by `__init__.py`. Contains `ConsentRecord` that takes raw `subject_id` (national ID) in request body — PII in transit. Completely superseded by `compliance.py` versions.

### H12. Duplicate Model Names Across Schema Modules
**AGENTS.md gap:** Not listed
**File:** `app/schemas/dataset.py` vs `app/schemas/catalog.py`
**Impact:** `DatasetResponse`, `DatasetBuildRequest`, `DatasetManifest`, `QuoteRequest`, `QuoteResponse` all exist in both files with different shapes. `__init__.py` only exports from `catalog.py`, silently shadowing `dataset.py` versions.

### H13. `buyer_id` in Client Payloads (Impersonation Risk)
**AGENTS.md confirmed:** Issue #12
**File:** `app/schemas/dataset.py:77`, `app/schemas/billing.py:14`
**Expanded:** Affects both `QuoteRequest` and `ExportRequest`. Buyers can impersonate each other by specifying another buyer's ID.

---

## MEDIUM — Race Conditions / Weak Validation / Operational Gaps

### M1. Double-Commit in `record_heartbeat` (Alert Loss)
**AGENTS.md confirmed:** Issue #14
**File:** `app/services/fleet.py:74-95`
**Expanded:** Heartbeat committed on line 72, audit alerts committed on lines 82-95 in separate transaction. If second commit fails, heartbeat recorded but audit alerts silently lost.

### M2. No Race Condition Protection on `submit_labels`
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:105-119`
**Impact:** Plain `SELECT` without `FOR UPDATE`. Two concurrent submissions could both pass `annotator_id` check and both write QA_REVIEW.

### M3. Duplicate Withdrawal Records from Concurrent Calls
**AGENTS.md gap:** Not listed
**File:** `app/services/compliance.py:69-95`
**Impact:** Two concurrent withdrawal requests for same subject_hash can both read same ACTIVE consents and create duplicate WITHDRAWN rows.

### M4. Batch Status Oscillation in `process_batch`
**AGENTS.md gap:** Not listed
**File:** `app/services/ingestion.py:189-204`
**Impact:** Unconditionally sets VALIDATING then INGESTED. If first commit succeeds and second fails, batch stuck in VALIDATING permanently.

### M5. `submit_review` Has No Self-Assignment Protection
**AGENTS.md gap:** Not listed
**File:** `app/services/annotation.py:132-174`
**Impact:** QA reviewer can review their own annotation. Guaranteed IAA=1.0. (Listed as C3 above, also medium operational issue.)

### M6. N+1 Query in `get_leaderboard()`
**AGENTS.md confirmed:** Issue #13
**File:** `app/services/annotation.py:356-365`
**Impact:** Fetches user separately for each annotator. Should use JOIN.

### M7. No Pagination on `/nodes/` and `/nodes/alerts`
**AGENTS.md confirmed:** Issue #16
**File:** `app/api/fleet.py`
**Impact:** Returns all nodes without limit. Will degrade as fleet scales.

### M8. IAA Threshold Hardcoded
**AGENTS.md confirmed:** Issue #20
**File:** `app/services/annotation.py:158`
**Impact:** Uses literal `0.96` instead of `settings.ANNOTATION_TARGET_IAA`.

### M9. Webhook Failure Not Queued for Retry
**AGENTS.md confirmed:** Issue #19
**File:** `app/services/billing.py:247-295`
**Impact:** Failed buyer notifications are only logged, never retried via background queue.

### M10. No CORS Configuration Validation
**AGENTS.md confirmed:** Issue #21
**File:** `app/main.py`
**Impact:** Empty `CORS_ORIGINS` defaults to localhost. May not be appropriate for production.

### M11. Schema Validation Gaps
**AGENTS.md gap:** Not listed
**Files:** Various schema files
**Impact:** Multiple fields lack proper constraints:
- `NodeRegister.latitude/longitude`: no range constraints (unlike `GeoPoint`)
- `NodeRegister.category`: bare `str` instead of `NodeCategory` enum
- `HeartbeatPayload` sensor values: no bounds (battery can be negative)
- `LoginRequest.password`: no `min_length` (unlike `UserCreate.password` which requires 8)
- `BatchUpload.batch_id`: no `max_length`
- `BatchValidation.checksum_sha256`: missing regex pattern that `BatchUpload` has
- `ExportRequest.buyer_id`: client-supplied (see H13)
- `ExportRequest.license_type`: bare `str` instead of enum
- `TimeRange`: no `start < end` validation
- `WeatherData.humidity_pct`: no 0-100 bounds
- `PaginatedResponse`: missing `from_attributes=True`

### M12. IAA Uses Unidirectional IoU
**AGENTS.md confirmed:** Issue #17
**File:** `app/services/annotation.py:279-322`
**Impact:** Systematically inflates scores when annotators disagree on number of objects.

### M13. MWK Wage Config Is Dead
**AGENTS.md gap:** Not listed
**File:** `app/core/config.py:32-33`, `app/workers/tasks.py:349-369`
**Impact:** `MWK_TO_USD_RATE` and `MINIMUM_ANNOTATOR_WAGE_MWK` are configured but never used. `pay_annotators_task` only counts certified annotations — no actual wage calculation.

### M14. Append-Only Enforcement Misdocumented
**AGENTS.md gap:** Not listed
**File:** `app/models/audit.py:3`
**Impact:** Comment claims "check constraint" but enforcement is via PostgreSQL triggers. Could mislead developers attempting to modify audit_logs.

### M15. No Explicit Tests for Append-Only Triggers
**AGENTS.md gap:** Not listed
**File:** test suite
**Impact:** No test attempts UPDATE/DELETE on consent_ledger or audit_logs to verify triggers fire.

---

## LOW — Code Quality / Documentation / Minor Issues

### L1. Deprecated `event_loop` Fixture Pattern
**File:** `tests/conftest.py:28-33`
**Impact:** Session-scoped `event_loop` is deprecated in modern pytest-asyncio.

### L2. `mock_minio` Fixture Defined but Never Used
**File:** `tests/conftest.py:58-63`
**Impact:** Dead code.

### L3. Silent Exception Swallowing in Tests
**File:** `tests/test_billing.py:56-60,124-131`, `tests/test_compliance.py:27-31,146-161`
**Impact:** Tests pass even when code under test throws exceptions.

### L4. Weak Assertion in IAA Test
**File:** `tests/test_annotation.py:101`
**Impact:** `pytest.raises((PermissionError, ValueError, Exception))` catches any exception.

### L5. `_create_node()` Helper Duplicated 4 Times
**Files:** `test_fleet.py`, `test_annotation.py`, `test_ingestion.py`, `test_compliance.py`
**Impact:** Should be shared fixture in conftest.py.

### L6. `get_node_detail` Imported but Never Called
**File:** `tests/test_fleet.py:11`
**Impact:** Dead import.

### L7. Inconsistent Schema Types Across Modules
**Files:** `dataset.py` vs `catalog.py` (same model names, different shapes)
**Impact:** Confusing and error-prone. `__init__.py` shadows some versions.

### L8. `LabelSubmission.labels` and `ReviewSubmission.review_labels` Are Untyped
**File:** `app/schemas/annotation.py:28,35`
**Impact:** No structure enforced on label payloads. Could accept arbitrary JSON.

### L9. `Detection.bbox` Allows Semantically Invalid Boxes
**File:** `app/schemas/common.py:39`
**Impact:** Bbox `[0.9, 0.9, 0.9, 0.9]` passes validation but extends past image boundaries.

### L10. No OpenAPI Customizations
**AGENTS.md confirmed:** Issue #24
**File:** `app/main.py`
**Impact:** Missing tags descriptions, examples, response models.

### L11. No Request/Response Compression
**AGENTS.md confirmed:** Issue #25
**Impact:** No gzip middleware.

### L12. No Metrics/Observability
**AGENTS.md confirmed:** Issue #26
**Impact:** No Prometheus metrics, no distributed tracing.

### L13. No CI/CD Pipeline Configuration
**AGENTS.md confirmed:** Issue #27
**Impact:** No GitHub Actions, GitLab CI, etc.

### L14. Celery Beat Schedule Not Defined
**AGENTS.md confirmed:** Issue #28
**Impact:** `celery_beat` service runs but no periodic tasks configured in code.

---

## AGENTS.md Issues Confirmed/Expanded

| AGENTS.md # | Status | Notes |
|-------------|--------|-------|
| #1 No pyproject.toml | **Confirmed** | Critical project infrastructure gap |
| #2 No README.md | **Confirmed** | Critical onboarding gap |
| #3 No LICENSE | **Confirmed** | Legal risk |
| #4 No CONTRIBUTING.md | **Confirmed** | Contribution barrier |
| #5 Hardcoded credentials | **Confirmed** | Security risk |
| #6 init_db() at startup | **Confirmed** | Should rely solely on Alembic |
| #7 Missing indexes | **Partially addressed** | Migration 0004 added some; may need more |
| #8 Race condition init_db/Alembic | **Confirmed** | |
| #9 /exports empty stub | **Confirmed** | Also see C1 (refund path missing) |
| #10 /exports/{id} placeholder | **Confirmed** | |
| #11 Invoice/receipt missing | **Confirmed** | |
| #12 buyer_id in payload | **Expanded** | Affects both QuoteRequest and ExportRequest (see H13) |
| #13 N+1 leaderboard | **Confirmed** | See M6 |
| #14 Double-commit heartbeat | **Expanded** | Alert loss risk (see M1) |
| #15 Rate limiter unbounded | **Confirmed** | |
| #16 No pagination nodes | **Confirmed** | See M7 |
| #17 Unidirectional IoU | **Confirmed** | See M12 |
| #18 No rate limit consent/withdraw | **Confirmed** | |
| #19 Webhook retry missing | **Confirmed** | See M9 |
| #20 IAA threshold hardcoded | **Confirmed** | See M8 |
| #21 CORS validation | **Confirmed** | See M10 |
| #22 Private import rate_limit | **Confirmed** | |
| #23 Missing type hints | **Confirmed** | |
| #24 No OpenAPI customizations | **Confirmed** | See L10 |
| #25 No compression | **Confirmed** | See L11 |
| #26 No metrics | **Confirmed** | See L12 |
| #27 No CI/CD | **Confirmed** | See L13 |
| #28 Celery beat empty | **Confirmed** | See L14 |
| #29 CQRS suggestion | **Confirmed** | Architecture suggestion |
| #30 Event sourcing consent | **Confirmed** | Architecture suggestion |
| #31 API versioning | **Confirmed** | Architecture suggestion |
| #32 Consent expiry background job | **Expanded** | Not just missing job — `EXPIRED` status is unreachable (see H2) |
| #33 Image processing stub | **Confirmed** | |
| #34 MinIO lifecycle policies | **Confirmed** | |

---

## Reusability Scorecard (New Countries/Verticals)

| Dimension | Score | Assessment |
|-----------|-------|------------|
| **Configuration** | 7/10 | Env-driven settings, but MWK-specific constants hardcoded in domain logic |
| **Data Model** | 6/10 | Generic enough (subject_hash, not national ID), but consent purposes are untyped |
| **Geography** | 4/10 | MWK rate hardcoded in config; jurisdiction premiums in catalog.py need new entries per country |
| **Authentication** | 8/10 | JWT + API key + node signature is flexible; no country-specific auth |
| **Compliance** | 3/10 | Consent model is Malawi-specific (single jurisdiction); no multi-jurisdiction consent handling |
| **Annotation** | 7/10 | IAA logic is jurisdiction-agnostic; needs real-world calibration per vertical |
| **Pricing** | 5/10 | Multiplier-based pricing is extensible, but geography premiums need expansion |
| **Billing** | 4/10 | Single currency (USD); MWK conversion unused; no multi-currency support |
| **Deployment** | 6/10 | Docker Compose is portable; but single-region assumptions in config |
| **Testing** | 4/10 | 60% endpoint coverage; many critical paths untested |

**Overall Reusability Score: 5.4/10** — Significant work needed for multi-country deployment.

### Key Reusability Gaps
1. **Single jurisdiction assumption** — Consent, compliance, and billing assume Malawi-only
2. **Hardcoded currency** — MWK_TO_USD_RATE is dead; no multi-currency support
3. **Geography premiums** — Need expansion strategy for new regions
4. **Consent purposes untyped** — Should be enum for cross-jurisdiction consistency
5. **No locale/i18n** — Error messages are English-only
6. **No timezone handling** — Assumes UTC throughout; field deployments need local time support

---

## Recommended Fix Order

### Phase 1: Critical Safety (Week 1)
1. **C1** — Implement refund path for failed/blocked exports
2. **C2** — Add status guard to `confirm_delivery`
3. **C3** — Add self-assignment protection to QA review
4. **C4/C5** — Add status guards to `submit_labels` and `submit_review`
5. **C6** — Migrate monetary fields to `Decimal` (or at minimum `Mapped[Decimal]`)
6. **C7** — Implement proper node health status transitions based on telemetry thresholds
7. **C8** — Implement dataset SOLD transition after successful export

### Phase 2: High Priority Logic Fixes (Week 2)
8. **H1** — Add FAILED status assignment when Celery retries exhaust
9. **H2** — Implement consent expiry background job + EXPIRED status transition
10. **H3** — Connect auto_label_task to annotation creation (or remove dead AUTO_LABELED status)
11. **H9** — Implement re-assignment cycle for rejected annotations
12. **H10** — Add row-level lock on credit check in `initiate_export`
13. **H11** — Delete dead `consent.py` schema file
14. **H12** — Consolidate duplicate schema modules

### Phase 3: Medium Priority Hardening (Week 3)
15. **M2** — Add `FOR UPDATE` to `submit_labels` annotation query
16. **M4** — Fix double-commit pattern in `process_batch`
17. **M11** — Add missing schema validators (lat/lng bounds, enum types, password min_length)
18. **M13** — Either implement wage calculation or remove dead config
19. **M14** — Fix audit.py comment to reference triggers, not check constraints
20. **M15** — Add explicit append-only trigger regression tests

### Phase 4: Testing & Quality (Week 4)
21. Fix silent exception swallowing in tests (L3)
22. Add tests for all missing endpoints (40% of endpoints untested)
23. Add tests for all 6 dead state transitions (H1-H8)
24. Add tests for refund path, credit race condition, and consent expiry
25. Fix deprecated `event_loop` fixture (L1)
26. Consolidate `_create_node()` helper (L5)

### Phase 5: Reusability & Scale (Month 2)
27. Multi-jurisdiction consent model
28. Multi-currency billing support
29. Expand geography premiums
30. Add locale/i18n framework
31. Implement missing Celery tasks (auto_label, export, payroll)
32. Add Prometheus metrics and distributed tracing

---

## Summary Statistics

| Category | Count |
|----------|-------|
| CRITICAL findings (new) | 8 |
| HIGH findings (new) | 13 |
| MEDIUM findings (new) | 15 |
| LOW findings (new) | 14 |
| **Total NEW findings** | **50** |
| AGENTS.md issues confirmed | 34/34 |
| AGENTS.md issues expanded | 6 |
| Dead states identified | 12 |
| Missing state transitions | 8 |
| Schema validation gaps | 11 |
| Test coverage gaps | ~40% of endpoints |
