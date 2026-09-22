# Deep Audit Findings — EdgeVision-MW Control Plane

**Audit Date:** 2026-07-26
**Re-audit Date:** 2026-08-16
**Scope:** Logic correctness, compliance, reliability, reusability, operability
**Baseline:** AGENTS.md 34-item known-issues list

---

## Re-audit Status (2026-08-16)

Re-verified every finding against the current codebase after Sprints 1–5
(smoothing/ReID, plate de-ID, event layer, road seg MVP + metric depth,
exporters + push alerting). **All 50 findings resolved** — every item that
was Partial/Open in the 2026-08-16 re-audit (H13, M1, M8, M10, M11, M12,
M14, L3, L5, L8, L9) was closed in the follow-up fix batch; N1–N10 also
resolved.

| ID | Finding | Status |
|----|---------|--------|
| C1 | No refund path | **Resolved** — `refund_escrow()` in `billing.py:24`, idempotent (double-refund guard), wired into retry-exhaust + consent-block paths |
| C2 | `confirm_delivery` no status guard | **Resolved** — status guard (`PENDING`/`PROCESSING` only) + `with_for_update()` (`billing.py:173-180`) |
| C3 | QA self-assignment bypass | **Resolved** — `annotator_id == reviewer_id` check (`annotation.py:187`) |
| C4 | `submit_labels` no status guard | **Resolved** — `HUMAN_REVIEW` guard + `with_for_update()` (`annotation.py:113-130`) |
| C5 | `submit_review` no status guard | **Resolved** — `QA_REVIEW` guard + `with_for_update()` (`annotation.py:160-172`) |
| C6 | Monetary values use float | **Resolved** — `Decimal` + `Numeric(12,2)` in `buyer.py:31`, `dataset.py:32`, `quote.py:18`; billing uses `Decimal` |
| C7 | Node status unconditionally ONLINE | **Resolved** — `_derive_node_status()` telemetry thresholds (`fleet.py:116`); OFFLINE background marking (`fleet.py:147`) |
| C8 | Revenue tracking dead (SOLD) | **Resolved** — SOLD + `sold_at` on delivery (`billing.py:210-211`); revenue queries by `sold_at` |
| H1 | FAILED export status unreachable | **Resolved** — retry-exhaust sets `ExportStatus.FAILED` (`tasks.py:779-780`) |
| H2 | EXPIRED consent status unreachable | **Resolved** — `expire_consents()` (`compliance.py:419`), append-only EXPIRED records |
| H3 | AUTO_LABELED status unreachable | **Resolved** — `auto_label_task` creates Annotation rows (`tasks.py:609`) |
| H4 | FOR_SALE status unreachable | **Resolved** — `publish_dataset()` gate (`catalog.py:372`) |
| H5 | PENDING batch unreachable | **Resolved** — batches created `PENDING` (`ingestion.py:114`) |
| H6 | REJECTED batch unreachable | **Resolved** — REJECTED on checksum/size failure (`ingestion.py:55,86`) |
| H7 | DEGRADED/MAINTENANCE/OFFLINE dead | **Resolved** — via C7 (telemetry-derived status + OFFLINE sweep) |
| H8 | VALIDATED ghost state | **Resolved** — `process_batch` transitions straight to INGESTED (`ingestion.py:265`) |
| H9 | No rework cycle | **Resolved** — `reassign_rejected()` (`annotation.py:437`) |
| H10 | Credit check TOCTOU | **Resolved** — `with_for_update()` on user (`billing.py:55,102`) |
| H11 | Duplicate `consent.py` schema | **Resolved** — file deleted |
| H12 | Duplicate schema names | **Resolved** — `dataset.py` now empty (0 classes); `catalog.py` sole source |
| H13 | `buyer_id` client-supplied | **Resolved** — `app/api/billing.py:39` overrides `export_data["buyer_id"] = user["sub"]`; `ExportRequest.buyer_id` no longer accepted |
| M1 | Heartbeat double-commit | **Resolved** — `record_heartbeat` single commit (`fleet.py`): `prev_heartbeat_at` read before update, alerts + audit rows written, one `db.commit()` |
| M2 | `submit_labels` race | **Resolved** — `with_for_update()` |
| M3 | Duplicate withdrawals race | **Resolved** — `with_for_update()` on consent query (`compliance.py:67-74`) |
| M4 | Batch status oscillation | **Resolved** — single INGESTED transition |
| M5 | Review self-assignment | **Resolved** — see C3 |
| M6 | N+1 leaderboard | **Resolved** — JOIN (`annotation.py:231-246`) |
| M7 | No pagination `/nodes/` | **Resolved** — `limit/offset` (`fleet.py:44,61`) |
| M8 | IAA threshold hardcoded | **Resolved** — `settings.ANNOTATION_TARGET_IAA` (`annotation.py:203`) |
| M9 | Webhook failure not retried | **Resolved** — `_notify_buyer` retry + audit (`billing.py:287`) |
| M10 | CORS validation | **Resolved** — production rejects the localhost fallback (`main.py:90-97`); `cors_origins_unset_in_production` warning logged |
| M11 | Schema validation gaps | **Resolved** — `NodeRegister` lat/lng bounds + `NodeCategory`/`PIIMode` enums + `node_id` length, `HeartbeatPayload` sensor bounds, `TimeRange` start<end, `WeatherData` bounds, `PaginatedResponse.from_attributes`, `BatchUpload.batch_id` length, `BatchValidation.checksum_sha256` pattern, `LicenseType` enums + `jurisdiction` |
| M12 | Unidirectional IoU | **Resolved** — symmetric best-match A→B and B→A (`annotation.py:343-355`) |
| M13 | MWK wage config dead | **Resolved** — wage + MWK→USD calc (`tasks.py:846-850`) |
| M14 | Append-only misdocumented | **Resolved** — `audit.py` comment now references the trigger enforcement |
| M15 | No append-only trigger tests | **Resolved** — UPDATE-block test in `test_compliance.py:177-180` |
| L1 | Deprecated `event_loop` fixture | **Resolved** — removed from conftest |
| L2 | `mock_minio` dead | **Resolved** — used by image/upload/road/studio tests |
| L3 | Silent exception swallowing in tests | **Resolved** — all `except Exception` blocks rewritten with deterministic `pytest.raises(HTTPException)` 402 asserts (`test_billing.py`); uncovered + fixed `dataset_id` FK bug in `billing.py` (used string identifier instead of `dataset.id`) |
| L4 | Weak IAA assertion | **Resolved** — replaced by concurrency test |
| L5 | `_create_node` duplicated | **Resolved** — single helper in `tests/conftest.py`; all 8 test files import it |
| L6 | Dead `get_node_detail` import | **Resolved** |
| L7 | Inconsistent schema types | **Resolved** — see H12 |
| L8 | Label payloads untyped | **Resolved** — `LabelSubmission.labels: list[AnnotationLabel]` (typed `class_name`/`confidence`/`bbox`, extra fields allowed); API serializes to JSON-safe dicts; schema tests in `tests/schemas/test_annotation_schema.py` |
| L9 | `Detection.bbox` invalid boxes | **Resolved** — zero-size and out-of-frame boxes rejected (`common.py` `validate_bbox`: w>0, h>0, x+w≤1, y+h≤1); tests in `tests/schemas/test_geometry.py` |
| L10 | No OpenAPI customizations | **Resolved** — description + `openapi_tags` (`main.py:53-56`) |
| L11 | No compression | **Resolved** — `GZipMiddleware` (`main.py:98`) |
| L12 | No metrics | **Resolved** — `/metrics` (`app/api/metrics.py`), incl. `ws_annotate_events_total` |
| L13 | No CI/CD | **Resolved** — `.github/workflows/ci.yml` |
| L14 | Celery beat not defined | **Resolved** — schedule in `app/workers/celery_app.py` |

**AGENTS.md known-issues re-check:** #1–4 (pyproject/README/LICENSE/CONTRIBUTING) resolved; #6 (`init_db`) resolved; #12/#13/#14/#16/#17/#19/#20/#26/#27/#28 resolved (see above); #5 (hardcoded creds) open; #33 (image processing) now integrated via road/depth/plate paths; remainder unchanged.

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

## New Findings (Sprints 3–5, 2026-08-16)

Findings introduced by / observed in the live-annotation, road-scene, export, and alerting work that landed since the original audit.

### N1 (MEDIUM) — Alert webhook delivery is synchronous in the live WS frame loop
**Files:** `app/api/ws_annotation.py` (`_dispatch_alert`), `app/services/alerts.py`
**Impact:** `_dispatch_alert` awaits `dispatch_event_alert` inside the frame-processing task; the webhook adapter has a 10 s httpx timeout, so a slow or saturated endpoint stalls live inference frames. Failures are swallowed (logged, not raised) so it never crashes the stream — but it can silently drop throughput.
**Fix:** dispatch via `asyncio.create_task` / background worker; return immediately to the frame loop.
**Resolved** — `_dispatch_alert` now runs as `asyncio.create_task(...)` (`ws_annotation.py`).

### N2 (MEDIUM) — Cityscapes export hardcodes 1920×1080 output dimensions
**Files:** `app/services/export_builder.py:173,447-448,699`
**Impact:** `_build_cityscapes_json` and `_preview_cityscapes` emit `imgWidth/imgHeight = 1920×1080` and scale polygons with `_cityscapes_polygon(d, 1920.0, 1080.0)` regardless of the source image size. For non-1080p source frames the polygon coordinates and declared dimensions disagree, corrupting downstream training.
**Fix:** thread actual `image_width/image_height` through the build/preview calls.
**Resolved** — `_image_dims(ann)` reads real dims (fallback 1920×1080); threaded through Cityscapes/COCO/VOC; `auto_label_task` stores `image_width`/`image_height` from `arr.shape`.

### N3 (MEDIUM, security) — Alert webhook URLs are unvalidated (SSRF vector)
**File:** `app/services/alerts.py`
**Impact:** `AlertChannel.config.url` accepts any string; `dispatch_event_alert` POSTs the event/rule envelope to it. An ADMIN (or compromised admin) can point a channel at internal endpoints (metadata services, localhost). No scheme or private-IP validation.
**Fix:** restrict to `http(s)`, block loopback/private/link-local ranges, validate at channel create/update time.
**Resolved** — `assert_safe_webhook_url` (http/https, host resolve via `getaddrinfo`, blocks loopback/private/link-local/multicast/reserved/unspecified) enforced by `validate_channel_config` in create/update; per-type config models + SSRF tests (`test_alerts_api.py`).

### N4 (MEDIUM, operational) — `/road/scene` runs ONNX segmentation synchronously per request
**File:** `app/api/road.py` (`analyze_road_scene_endpoint`)
**Impact:** Each call fetches the image from MinIO, runs the segmenter, builds the metric depth map, and analyzes the scene inside the request handler. Slow on edge-class hardware; no background job or caching.
**Fix:** background task + status polling (mirror `prelabel`/`segment/batch` pattern) or result cache keyed by image_id + calibration.
**Resolved** — heavy ONNX inference moved into a sync closure executed via `asyncio.to_thread` (`road.py`).

### N5 (LOW) — `close_approach` silently never fires when metric depth is unavailable
**File:** `app/ai/events.py:490`
**Impact:** The DISTANCE rule reads `det.get("distance_m")`; when a box has no metric depth (`below_horizon_unknown`), the rule returns `None` with no warning. Operators see no events and may assume the rule works.
**Fix:** log/surface a `distance_unavailable` signal or a per-rule counter (`ws_annotate_events_total` label).
**Resolved** — DISTANCE branch logs `distance_missing` and the engine exposes `distance_unrated_by_rule` in `state_summary()`; test added.

### N6 (LOW) — SMS/PUSH alert adapters are structured-log stubs
**File:** `app/services/alerts.py` (`_deliver_sms`, `_deliver_push`)
**Impact:** Both return `delivered=False, reason="..._provider_not_configured"`. Intentional (no provider credentials in this deployment) but a configured SMS/PUSH channel silently never delivers.
**Fix:** wire provider adapters (Twilio/FCM-style) behind env-configurable credentials.
**Resolved** — `_deliver_sms`/`_deliver_push` POST `{"config":…, "alert":…}` to `SMS_PROVIDER_URL`/`PUSH_PROVIDER_URL` when configured, else stub; provider-path test added.

### N7 (LOW) — Metric depth assumes flat-ground pinhole with fixed defaults
**File:** `app/ai/metric_depth.py`
**Impact:** `z = h·f / (row − horizon)` with defaults `h=1.5 m, f=700 px, horizon=0.35`; no roll/pitch compensation. Unleveled or off-axis cameras bias `distance_m` and the `road_edge_distance_m` metric.
**Fix:** accept per-camera calibration (already optional per-request) and document roll correction.
**Resolved** — module docstring documents the flat-ground assumption and limits.

### N8 (LOW) — `decode_mask_rle` bbox-fill fallback yields coarse geometry
**File:** `app/ai/road_semantic.py`
**Impact:** When pycocotools is unavailable or RLE decode fails, masks fall back to the detection bbox → sidewalk/curb geometric heuristics and drivable-ratio are rough approximations.
**Fix:** log a quality downgrade and expose `mask_quality` in the scene response.
**Resolved** — `_as_mask` returns a `mask_quality` (`rle`/`bbox_fill`/`none`); exposed on hazards + scene via `RoadScene.mask_quality`/`RoadSceneHazard.mask_quality`.

### N9 (LOW) — `AlertChannel.config` is unvalidated free-form JSON
**File:** `app/api/alerts.py` (`AlertChannelCreate.config: dict`)
**Impact:** Typo'd/absent keys (`url`, `phone`, `push_token`) fail only at dispatch time; no schema per channel_type.
**Fix:** per-type config schema validation (Pydantic discriminated union).
**Resolved** — typed union `WebhookChannelConfig|SmsChannelConfig|PushChannelConfig|dict` with `model_validator(mode="before")`; service-side `validate_channel_config` enforces on create/update (422).

### N10 (INFO) — KITTI exporter uses `-1.0` placeholders for missing 3D geometry
**File:** `app/services/export_builder.py` (`_kitti_line`)
**Impact:** Detections without `bbox_3d` emit `h w l x y z rotation_y = -1.0`, which is the KITTI convention for "unknown" — acceptable, but consumers must handle it.
**Fix:** none required; document the convention.
**Resolved** — documented in `_build_kitti_txt` docstring.

---

## Recommended Fix Order

### Re-audit status (2026-08-16)
All C1–C8 and H1–H12 resolved. Remaining priority:

1. **H13** — Derive `buyer_id` from the authenticated token in `initiate_export` (impersonation fix)
2. **N3** — Alert webhook URL validation (SSRF)
3. **N1** — Background-dispatch alert webhooks off the WS frame loop
4. **N2** — Cityscapes export real image dimensions
5. **N4** — Background `/road/scene` processing
6. **M8** — Use `settings.ANNOTATION_TARGET_IAA` instead of literal `0.96`
7. **M14** — Correct `audit.py` append-only comment (trigger, not check constraint)
8. **M12** — Bidirectional IoU matching in `_iou_agreement`
9. **M11** — NodeRegister lat/lng bounds + category enum; `TimeRange`; `WeatherData.humidity_pct`; `PaginatedResponse.from_attributes`
10. **N5–N9, M1, M10, L3, L5, L8, L9** — follow-ups (see status table)

**All items above are now Resolved (2026-08-17).** No remaining C/H/M/L/N findings.
Open items are now only the AGENTS.md known-issues not yet addressed (#5 hardcoded creds; #7 indexes; #8 init_db/Alembic race; #9/#10 export stubs; #11 invoices; #15 unbounded rate limiter; #18 no consent/withdraw rate limit; #22 private import; #23 type hints; #29–34 architecture suggestions).

### Original phased plan (kept for reference, mostly executed)

### Phase 1: Critical Safety (Week 1)
1. **C1** — Implement refund path for failed/blocked exports — **DONE**
2. **C2** — Add status guard to `confirm_delivery` — **DONE**
3. **C3** — Add self-assignment protection to QA review — **DONE**
4. **C4/C5** — Add status guards to `submit_labels` and `submit_review` — **DONE**
5. **C6** — Migrate monetary fields to `Decimal` — **DONE**
6. **C7** — Implement proper node health status transitions based on telemetry thresholds — **DONE**
7. **C8** — Implement dataset SOLD transition after successful export — **DONE**

### Phase 2: High Priority Logic Fixes (Week 2)
8. **H1** — Add FAILED status assignment when Celery retries exhaust — **DONE**
9. **H2** — Implement consent expiry background job + EXPIRED status transition — **DONE**
10. **H3** — Connect auto_label_task to annotation creation — **DONE**
11. **H9** — Implement re-assignment cycle for rejected annotations — **DONE**
12. **H10** — Add row-level lock on credit check in `initiate_export` — **DONE**
13. **H11** — Delete dead `consent.py` schema file — **DONE**
14. **H12** — Consolidate duplicate schema modules — **DONE**

### Phase 3: Medium Priority Hardening (Week 3)
15. **M2** — Add `FOR UPDATE` to `submit_labels` annotation query — **DONE**
16. **M4** — Fix double-commit pattern in `process_batch` — **DONE**
17. **M11** — Add missing schema validators (lat/lng bounds, enum types, password min_length) — **DONE** (incl. TimeRange, WeatherData, PaginatedResponse, LicenseType, batch/checksum constraints)
18. **M13** — Implement wage calculation — **DONE**
19. **M14** — Fix audit.py comment to reference triggers — **DONE**
20. **M15** — Add explicit append-only trigger regression tests — **DONE**

### Phase 4: Testing & Quality (Week 4)
21. Fix silent exception swallowing in tests (L3) — **DONE** (deterministic 402 asserts; surfaced + fixed `dataset_id` FK bug)
22. Add tests for all missing endpoints — **DONE** (full suite now 460 passed, 2 skipped)
23. Add tests for all 6 dead state transitions (H1-H8) — **DONE**
24. Add tests for refund path, credit race condition, and consent expiry — **DONE**
25. Fix deprecated `event_loop` fixture (L1) — **DONE**
26. Consolidate `_create_node()` helper (L5) — **DONE** (shared `tests/conftest.py` fixture)

### Phase 5: Reusability & Scale (Month 2)
27. Multi-jurisdiction consent model — **OPEN**
28. Multi-currency billing support — **OPEN**
29. Expand geography premiums — **OPEN**
30. Add locale/i18n framework — **DONE** (frontend i18n en/ny)
31. Implement missing Celery tasks (auto_label, export, payroll) — **DONE**
32. Add Prometheus metrics and distributed tracing — **PARTIAL** (metrics done; tracing missing)

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

## Re-audit Summary (2026-08-16)

| Metric | Value |
|--------|-------|
| Findings resolved since original audit | **27 / 50** |
| Findings partially addressed | 12 |
| Findings still open | 11 |
| CRITICAL/HIGH remaining | 1 (H13) + 0 critical |
| New findings from Sprints 3–5 | 10 (N1–N10; 4 medium, 5 low, 1 info) |
| Full backend test suite | **448 passed, 2 skipped** (up from partial coverage) |
| Frontend | `tsc --noEmit` + production build clean |

## Re-audit Summary (2026-08-17, follow-up fix batch)

| Metric | Value |
|--------|-------|
| Findings resolved since original audit | **50 / 50** (all Open/Partial items closed) |
| Findings partially addressed | 0 |
| Findings still open | 0 |
| CRITICAL/HIGH remaining | 0 |
| New findings from Sprints 3–5 | 10 (N1–N10) — all resolved |
| Full backend test suite | **460 passed, 2 skipped** |
| Frontend | `tsc --noEmit` + production build clean |
| Real defects surfaced by test hardening | 2 (`dataset_id` FK bug in `billing.py`; list-vs-dict `human_labels` wiring) — fixed |
