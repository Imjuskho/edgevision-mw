# AGENTS.md — EdgeVision-MW Control Plane

This document provides a comprehensive, AI-readable reference for the EdgeVision-MW Control Plane codebase. It is intended for AI assistants (Claude, GPT, Copilot, etc.) to understand the project's architecture, conventions, domain model, and improvement opportunities.

---

## 1. Project Overview

**EdgeVision-MW** is a **control plane** for a distributed edge-computing data platform deployed across rural Malawi. The system manages a fleet of solar-powered edge devices (nodes) that capture road, agricultural, wildlife, documentary, and biometric imagery. Captured data flows through ingestion, human-in-the-loop annotation, quality assurance, dataset assembly, and finally to a data marketplace where international buyers purchase licensed datasets.

The platform enforces **privacy-by-design** through append-only consent ledgers, PII detection, inter-annotator agreement (IAA) scoring, and jurisdiction-aware export controls.

**Tech Stack:**
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Celery
- PostgreSQL 16, Redis 7, MinIO (S3-compatible object storage)
- Docker Compose for orchestration, Alembic for migrations
- structlog for structured logging, bcrypt/Ed25519 for security

**Project Root:** `edgevision-mw/`

---

## 2. Directory Structure

```
edgevision-mw/
├── app/
│   ├── main.py                  # FastAPI application, lifespan, middleware, health check
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (env-driven configuration)
│   │   ├── database.py          # SQLAlchemy engine, session factory, Base, mixins
│   │   ├── security.py          # JWT, bcrypt, Ed25519 signature verification
│   │   ├── dependencies.py      # FastAPI deps: auth, Redis, MinIO, node auth
│   │   ├── exceptions.py        # Custom exception classes + handlers
│   │   ├── rate_limit.py        # Sliding window rate limiter (Redis + in-memory fallback)
│   │   └── logging.py           # structlog setup (JSON in prod, console in dev)
│   ├── auth/
│   │   ├── router.py            # /auth/* endpoints: register, login, API keys, /me
│   │   └── service.py           # User creation, authentication, API key management
│   ├── api/
│   │   ├── __init__.py          # Router registry
│   │   ├── fleet.py             # /nodes/* — heartbeat, fleet status, alerts, telemetry
│   │   ├── ingestion.py         # /ingest/* — batch upload, validation, queue stats
│   │   ├── annotation.py        # /jobs/* — assignment, label submission, QA review, leaderboard
│   │   ├── catalog.py           # /datasets/* — search, build, manifest, quotes
│   │   ├── compliance.py        # /consent/* — record, withdraw, verify, audit, PII check
│   │   └── billing.py           # /exports, /billing/* — export, delivery, revenue
│   ├── services/
│   │   ├── fleet.py             # Heartbeat recording, health alerts, telemetry queries
│   │   ├── ingestion.py         # Batch receive, validate, process, queue stats
│   │   ├── annotation.py        # Auto-assign, label submission, QA review, IAA calculation
│   │   ├── catalog.py           # Dataset search, build, pricing, quote generation
│   │   ├── compliance.py        # Consent CRUD, withdrawal cascade, PII audit, daily audit
│   │   └── billing.py           # Export initiation, payment escrow, delivery, webhooks
│   ├── models/
│   │   ├── __init__.py          # All model re-exports
│   │   ├── enums.py             # All enum definitions (NodeCategory, BatchStatus, etc.)
│   │   ├── node.py              # Node — edge device registration
│   │   ├── heartbeat.py         # Heartbeat — device telemetry records
│   │   ├── ingestion.py         # IngestionBatch — data upload batches
│   │   ├── annotation.py        # Annotation + AnnotationAssignment — labeling jobs
│   │   ├── subject.py           # SubjectAnnotation — subject-to-annotation junction table
│   │   ├── dataset.py           # Dataset — assembled datasets for sale
│   │   ├── buyer.py             # User + BuyerApiKey — accounts and API access
│   │   ├── export.py            # Export + ExportLog — data delivery records
│   │   ├── consent.py           # ConsentLedger — append-only consent records
│   │   ├── audit.py             # AuditLog — append-only audit trail
│   │   └── quote.py             # Quote — dataset pricing quotes
│   ├── schemas/
│   │   ├── common.py            # Shared: GeoPoint, Detection, PaginatedResponse, ErrorResponse
│   │   ├── node.py              # HeartbeatPayload, NodeCommand, NodeStatus, etc.
│   │   ├── ingestion.py         # BatchUpload, BatchResponse, ValidationResult, IngestionQueue
│   │   ├── annotation.py        # LabelSubmission, ReviewSubmission, AnnotatorLeaderboard
│   │   ├── catalog.py           # DatasetResponse, DatasetBuildRequest, QuoteRequest/Response
│   │   ├── compliance.py        # ConsentRecord, ConsentVerification, PIICheckResult
│   │   ├── billing.py           # ExportRequest, ExportResponse, RevenueBreakdown
│   │   ├── auth.py              # LoginRequest, UserCreate, TokenResponse, APIKeyCreate
│   │   ├── consent.py           # (empty or minimal — consent schemas in compliance.py)
│   │   └── dataset.py           # (empty or minimal — dataset schemas in catalog.py)
│   └── workers/
│       ├── celery_app.py        # Celery application config
│       └── tasks.py             # 22 async tasks: batch, dataset, audit, auto-label, export, training, dedup, consent, perception, and more
├── tests/
│   ├── conftest.py              # Fixtures: db_session, test_client, jwt_token_factory, mock_minio
│   ├── test_fleet.py
│   ├── test_ingestion.py
│   ├── test_annotation.py
│   ├── test_catalog.py
│   ├── test_compliance.py
│   ├── test_billing.py
│   ├── test_auth.py
│   ├── test_rate_limit.py
│   ├── test_buyer_notification.py
│   └── schemas/
│       └── test_geometry.py
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_append_only_enforcement.py
│       ├── 0003_add_webhook_url.py
│       ├── 0004_composite_indexes.py
│       ├── 0005_add_subject_annotations.py
│       ├── 0006_drop_consent_ledger_updated_at.py
│       └── 0007_add_quotes_table.py
├── scripts/
│   ├── backup.sh                # PostgreSQL + Redis + MinIO backup script
│   └── activation/              # Production activation scripts
│       ├── register_node.py     # P1.1: Register a real node + first heartbeat
│       ├── process_batch.py     # P1.2: Create batch + dispatch auto_label via Celery
│       ├── validate_yolo.py     # P2.1: Validate YOLO on real frames with precision/recall/F1
│       ├── generate_report.py   # P4.1: Generate municipal weekly report (JSON + CSV)
│       ├── daily_check.py       # Daily discipline: 3 numbers + fleet health + alerts
│       ├── collect_field_data.py # Phone+Car workflow: GPS extraction, video frames, dedup, batch
│       └── FIELD_GUIDE.md       # Step-by-step field collection guide for operators
├── docs/
│   ├── annotator-onboarding-guide.md
│   ├── production-deployment-guide.md
│   ├── field-deployment-checklist-lilongwe.md
│   └── buyer-pitch-deck-outline.md
├── Dockerfile                   # Multi-stage build (builder + runtime)
├── docker-compose.yml           # 6 services: app, celery_worker, celery_beat, postgres, redis, minio
├── entrypoint.sh                # Wait for Postgres → Alembic migrate → start uvicorn
├── requirements.txt
├── alembic.ini
├── .env                         # (gitignored — actual secrets)
└── .env.example                 # Documented environment variable template
```

---

## 3. Domain Model (14 SQLAlchemy Models)

### Core Entities
| Model | Table | Purpose | Key Fields |
|-------|-------|---------|------------|
| `Node` | `nodes` | Edge device registration | `node_id` (str, unique), `district`, `lat/lng`, `category`, `hardware_profile` (JSONB), `pii_mode`, `public_key` (bytes), `status` |
| `Heartbeat` | `heartbeats` | Device telemetry | `node_id` (FK), `battery_voltage`, `cpu_temp_celsius`, `storage_used_gb`, `lte_rssi_dbm`, `events_captured/uploaded` |
| `IngestionBatch` | `ingestion_batches` | Data upload batches | `batch_id` (str, unique), `node_id` (FK), `checksum_sha256`, `node_signature`, `status`, `quality_scores` (JSONB) |
| `Annotation` | `annotations` | Labeling jobs | `batch_id` (FK), `image_path`, `detected_objects`, `auto_labels`, `human_labels`, `qa_labels`, `status`, `iaa_score`, `annotator_id` (FK→users), `dataset_id` (FK→datasets) |
| `AnnotationAssignment` | `annotation_assignments` | Job assignments | `annotation_id` (FK), `annotator_id` (FK), `assigned_at`, `deadline`, `is_active` |
| `SubjectAnnotation` | `subject_annotations` | Subject↔annotation junction (append-only) | `subject_hash` (indexed), `annotation_id` (FK), `dataset_id` (FK), `confidence` |
| `Dataset` | `datasets` | Assembled datasets | `dataset_id` (str, unique), `name`, `status`, `sample_count`, `classes` (JSONB), `price_usd`, `license_type`, `consent_coverage_pct`, `iaa_score` |
| `User` | `users` | User accounts | `email` (unique), `hashed_password`, `role`, `api_key_hash`, `jurisdiction`, `dpa_signed`, `credit_balance_usd`, `webhook_url` |
| `BuyerApiKey` | `buyer_api_keys` | API keys for buyers | `user_id` (FK), `key_hash`, `scopes` (ARRAY), `expires_at` |
| `Export` | `exports` | Data delivery records | `dataset_id` (FK), `buyer_id` (FK), `license_key`, `status`, `price_usd`, `watermark_fingerprint`, `formats_delivered` (ARRAY) |
| `ExportLog` | `export_logs` | Export event log | `export_id` (FK), `event_type`, `details` (JSONB) |
| `ConsentLedger` | `consent_ledger` | Append-only consent records | `subject_hash` (indexed), `tx_hash` (unique), `purposes` (ARRAY), `status`, `signature_bytes`, `expiry` |
| `AuditLog` | `audit_logs` | Append-only audit trail | `event_type`, `severity`, `actor_id`, `actor_type`, `resource_type`, `resource_id`, `details` (JSONB), `ip_address` |
| `Quote` | `quotes` | Dataset pricing quotes | `buyer_id` (FK), `dataset_id` (str), `base_price_usd`, `exclusivity_multiplier`, `geography_premium`, `total_price_usd`, `license_type`, `expires_at` |

### Key Relationships
```
Node 1──N Heartbeat
Node 1──N IngestionBatch
IngestionBatch 1──N Annotation
User 1──N Annotation (as annotator)
User 1──N Annotation (as QA reviewer)
Annotation N──1 Dataset
Annotation 1──N AnnotationAssignment
SubjectAnnotation junction: subject_hash ↔ annotation_id ↔ dataset_id
User 1──N BuyerApiKey
User 1──N Export
Dataset 1──N Export
Export 1──N ExportLog
```

### Append-Only Tables
- `consent_ledger`: PostgreSQL trigger blocks UPDATE/DELETE. Withdrawal = new row with `status=WITHDRAWN`.
- `audit_logs`: Check constraint enforces append-only. Only INSERT.

### Enums (app/models/enums.py)
- `NodeCategory`: ROAD, AGRI, WILDLIFE, DOC, BIOMETRIC
- `NodeStatus`: ONLINE, OFFLINE, DEGRADED, MAINTENANCE
- `PIIMode`: STRICT, MODERATE, NONE
- `BatchStatus`: PENDING → VALIDATING → VALIDATED → INGESTED / REJECTED
- `AnnotationStatus`: PENDING → AUTO_LABELED → HUMAN_REVIEW → QA_REVIEW → CERTIFIED / REJECTED
- `DatasetStatus`: BUILDING → READY → FOR_SALE → SOLD / RETRACTED
- `ExportStatus`: PENDING → PROCESSING → COMPLETED / FAILED / BLOCKED
- `UserRole`: ADMIN, OPERATOR, ANNOTATOR, QA, BUYER, FIELD_TECH
- `ConsentStatus`: ACTIVE, WITHDRAWN, EXPIRED
- `LicenseType`: PERPETUAL, ANNUAL, EXCLUSIVE

---

## 4. API Endpoints

All routes are prefixed with `/api/v1`.

### Auth (`/auth`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | None | Register new user (always BUYER role) |
| POST | `/auth/login` | None | Login → JWT access token |
| POST | `/auth/api-keys` | Bearer | Create API key |
| GET | `/auth/api-keys` | Bearer | List active API keys (redacted) |
| GET | `/auth/me` | Bearer | Get current user profile |

### Fleet (`/nodes`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/nodes/heartbeat` | Node Ed25519 | Submit heartbeat + receive commands |
| GET | `/nodes/` | Bearer | List all nodes (filter by district, category, status) |
| GET | `/nodes/alerts` | Bearer | Active health alerts |
| GET | `/nodes/{node_id}` | Bearer | Node detail + recent heartbeats |
| POST | `/nodes/{node_id}/command` | Bearer | Queue command for next heartbeat |
| GET | `/nodes/{node_id}/telemetry` | Bearer | Time-series telemetry (hours param) |

### Ingestion (`/ingest`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/ingest/batch` | Node Ed25519 | Upload batch (idempotent by batch_id) |
| GET | `/ingest/queue` | Bearer | Queue statistics |
| POST | `/ingest/validate` | Node Ed25519 | Validate batch before upload |
| GET | `/ingest/batches` | Bearer | List batches (filter by node, status, date) |
| GET | `/ingest/batches/{batch_id}` | Bearer | Batch detail |

### Annotation (`/jobs`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/jobs/assign` | ADMIN/QA | Auto-assign pending jobs (workload-balanced) |
| POST | `/jobs/{job_id}/submit` | ANNOTATOR | Submit human labels |
| POST | `/jobs/{job_id}/review` | QA/ADMIN | Submit QA review + compute IAA |
| GET | `/jobs/leaderboard` | Bearer | Annotator leaderboard (date range) |
| GET | `/jobs/pending` | ANNOTATOR | My pending jobs |
| GET | `/jobs/{job_id}` | Bearer | Job detail |

### Catalog (`/datasets`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/datasets/` | Buyer/Any | Search datasets (paginated) |
| POST | `/datasets/build` | ADMIN/OPERATOR | Trigger dataset build (async Celery) |
| GET | `/datasets/{dataset_id}` | Bearer | Dataset detail |
| GET | `/datasets/{dataset_id}/manifest` | Buyer/Any | COCO-format manifest |
| POST | `/datasets/quotes` | Buyer/Any | Generate pricing quote |
| GET | `/datasets/quotes/{quote_id}` | Bearer | Get quote detail |

### Compliance (`/consent`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/consent/record` | ADMIN/OPERATOR/FIELD_TECH | Record new consent |
| POST | `/consent/withdraw` | ADMIN/OPERATOR | Withdraw consent (cascading block) |
| GET | `/consent/verify` | Bearer | Verify consent for purpose |
| GET | `/consent/audit` | ADMIN | Run daily compliance audit |
| POST | `/consent/pii/audit` | ADMIN/QA | PII detection check on dataset |

### Billing (`/exports`, `/billing`, `/webhooks`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/exports` | BUYER/ADMIN | Initiate dataset export (payment escrow) |
| GET | `/exports` | Buyer/Any | List exports (placeholder) |
| GET | `/exports/{export_id}` | Bearer | Get export detail (placeholder) |
| GET | `/billing/revenue` | ADMIN | Revenue breakdown by period |
| POST | `/webhooks/buyer` | Bearer | Confirm delivery webhook |

---

## 5. Authentication & Authorization

### Three Auth Methods
1. **JWT Bearer Token** — Used by human users (admin, annotators, QA, buyers). Token contains `sub` (user UUID), `role`, `email`. Standard `HTTPBearer` scheme.
2. **API Key (X-API-Key header)** — Used by buyer integrations. Key is SHA-256 hashed for lookup. Supports scopes and expiration.
3. **Node Signature (Ed25519)** — Used by edge devices. Headers: `X-Node-ID`, `X-Node-Timestamp`, `X-Node-Signature`, `X-Node-Public-Key`. Timestamp freshness check (60s window) for replay protection.

### Role-Based Access
- `require_role(["ADMIN", "QA"])` — Dependency factory for role checking
- Roles: ADMIN (full access), OPERATOR (ops tasks), ANNOTATOR (labeling), QA (review), BUYER (data purchase), FIELD_TECH (consent recording)

### Key Dependency Functions
- `get_current_user` — Extracts JWT payload
- `require_role(roles)` — Returns dependency that checks role membership
- `require_node_auth` — Ed25519 signature verification with replay protection
- `get_current_buyer` — API key verification
- `get_current_buyer_or_user` — Accepts either JWT or API key

---

## 6. Core Infrastructure

### Configuration (app/core/config.py)
- All settings via environment variables with sensible defaults
- `.env` file support via pydantic-settings
- `SECRET_KEY` is mandatory (raises ValueError if not set)
- `DATABASE_URL` auto-built from component parts
- Key business constants: `ANNOTATION_TARGET_IAA=0.96`, `MINIMUM_ANNOTATOR_WAGE_MWK=5000`, `MWK_TO_USD_RATE=0.0006`

### Database (app/core/database.py)
- Async SQLAlchemy with `asyncpg` driver
- Connection pool: 20 connections, 10 overflow, 30s timeout, 1800s recycle, pre-ping enabled
- `Base` class auto-generates table names from class names (lowercase + "s")
- `TimestampMixin` — `created_at` + `updated_at` (timezone-aware)
- `AppendOnlyMixin` — `created_at` only (for immutable tables)
- `init_db()` is a no-op; schema is managed exclusively by Alembic migrations

### Rate Limiting (app/core/rate_limit.py)
- Sliding window algorithm with Redis sorted sets
- In-memory fallback when Redis is unavailable
- Path-based rules with identity resolution:
  - `/auth/login`: 5 req/min (by IP)
  - `/nodes/heartbeat`: 60 req/min (by node ID)
  - `/ingest/batch`: 10 req/min (by IP)
  - `/datasets/search`: 100 req/min (by API key or IP)
  - `/datasets/quotes`: 20 req/min (by API key or IP)
  - `/exports`: 5 req/min (by API key or IP)
  - `/jobs/assign`: 30 req/min (by Bearer token hash)

### Logging (app/core/logging.py)
- `structlog` with request ID context var
- Production: JSON renderer; Development: Console renderer
- Request middleware assigns UUID to each request, logs method/path/status/duration

### Exception Handling (app/core/exceptions.py)
- Custom hierarchy: `AppError` → `NotFoundError`, `ConflictError`, `PermissionDeniedError`, `AuthenticationError`
- Structured validation error responses with field-level messages
- Unhandled exceptions logged with full traceback, returns generic 500

---

## 7. Background Workers (Celery)

### Celery Config (app/workers/celery_app.py)
- Broker & backend: Redis (`redis://redis:6379/1`)
- JSON serialization, UTC timezone
- `task_acks_late=True`, `worker_prefetch_multiplier=1` (fair scheduling)
- Soft time limit: 600s, hard time limit: 900s

### Tasks (app/workers/tasks.py)
All tasks use `_run_async()` helper (`asyncio.run()`) to bridge sync Celery → async service layer.

| Task Name | Function | Description |
|-----------|----------|-------------|
| `workers.process_batch` | `process_batch_task` | Transition batch VALIDATING → INGESTED |
| `workers.build_dataset` | `build_dataset_task` | Build dataset: stratified sampling, class balancing, PII check, pricing |
| `workers.run_compliance_audit` | `run_compliance_audit_task` | Daily consent audit (count active/withdrawn/expired) |
| `workers.auto_label` | `auto_label_task` | YOLO prelabel + YOLOv8-seg masks (SAM when decoder probe passes); batch → INGESTED + Annotation rows |
| `workers.auto_label_annotations` | `auto_label_annotations_task` | Auto-label existing annotations with vision models |
| `workers.export_dataset` | `export_dataset_task` | Secure export: PENDING → PROCESSING → COMPLETED with ExportLog |
| `workers.pay_annotators` | `pay_annotators_task` | Weekly payment: count certified annotations per annotator |
| `workers.run_training` | `run_training_task` | Model training job orchestration |
| `workers.check_heartbeat_timeouts` | `check_heartbeat_timeouts_task` | Detect and alert on nodes missing heartbeats |
| `workers.reconcile_stuck_batches` | `reconcile_stuck_batches_task` | Recover batches stuck in non-terminal states |
| `workers.dedup_analyze` | `dedup_analyze_task` | Cross-dataset deduplication analysis |
| `workers.export_build` | `export_build_task` | Build export archive with watermarking |
| `workers.auto_label_road` | `auto_label_road_task` | Road-specific auto-labeling pipeline |
| `workers.auto_label_agri` | `auto_label_agri_task` | Agriculture-specific auto-labeling pipeline |
| `workers.expire_consents` | `expire_consents_task` | Expire consents past their expiry date |
| `workers.hard_delete_user_data` | `hard_delete_user_data_task` | GDPR-compliant hard delete of user data |
| `workers.process_operator_stipends` | `process_operator_stipends_task` | Calculate and disburse operator stipends |
| `workers.daily_consent_sms_digest` | `daily_consent_sms_digest_task` | Daily consent status SMS summary |
| `workers.process_airtime_rewards` | `process_airtime_rewards_task` | Disburse mobile airtime rewards to annotators |
| `workers.predict_trajectories` | `predict_trajectories_task` | Vehicle trajectory prediction from camera feeds |
| `workers.detect_anomalies` | `detect_anomalies_task` | Real-time anomaly detection on camera frames |
| `workers.update_scene_reconstruction` | `update_scene_reconstruction_task` | 3D scene reconstruction from multi-view imagery |

All tasks have: `autoretry_for=(Exception,)`, `max_retries=3`, `retry_backoff=True`, `retry_jitter=True`. Audit logs written on success and failure.

---

## 8. Key Business Logic

### IAA Calculation (app/services/annotation.py)
- **Object Detection**: IoU-based agreement on bounding boxes (mean IoU across best-matched pairs)
- **Biometric/Classification**: Cohen's Kappa
- Threshold: `>= 0.96` → CERTIFIED; `< 0.96` → REJECTED
- IAA computed server-side (never trusted from client)

### Dataset Pricing (app/services/catalog.py)
- Base: `$0.30 × sample_count × complexity`
- Exclusivity multipliers: ANNUAL=1.0, PERPETUAL=1.5, EXCLUSIVE=2.5
- Geography premiums: MW=1.0, US/GB=1.3, EU=1.2, DEFAULT=1.1

### Consent Withdrawal Cascade (app/services/compliance.py)
1. Insert withdrawal records (append-only — cannot UPDATE existing consents)
2. Find annotations linked to subject via `SubjectAnnotation` junction table
3. Set matching annotations to REJECTED status
4. Block pending exports containing affected datasets
5. Write audit log with full impact summary

### PII Detection (app/services/compliance.py)
- Checks annotation labels for `faces` and `license_plates` keys
- Optional ONNX Runtime model (checked once, cached)
- Falls back to label-based detection when model not available
- Writes audit log if PII detected

### Annotation Assignment (app/services/annotation.py)
- `SELECT ... FOR UPDATE SKIP LOCKED` to prevent double-assignment
- Workload-balanced: annotators sorted by active assignment count (least busy first)
- 48-hour deadline per assignment
- Round-robin fallback when multiple annotators have equal workload

---

## 9. DevOps & Deployment

### Docker Compose Services
1. **app** — FastAPI application (port 8000)
2. **celery_worker** — Celery worker (concurrency=4)
3. **celery_beat** — Celery beat scheduler
4. **postgres** — PostgreSQL 16 Alpine
5. **redis** — Redis 7 Alpine (password-protected)
6. **minio** — MinIO S3-compatible storage (ports 9000, 9001)

### Entrypoint Flow
1. Wait for PostgreSQL (`pg_isready`)
2. Run Alembic migrations (`alembic upgrade head`)
3. Start Uvicorn

### Dockerfile
- Multi-stage build: builder (gcc + libpq-dev) → runtime (libpq5 + curl)
- Non-root user (`appuser`)
- Health check: `curl -f http://localhost:8000/health`

### Backup Script (scripts/backup.sh)
- PostgreSQL: `pg_dump` + `pg_dumpall --globals-only` (gzipped)
- Redis: `BGSAVE` + `docker cp`
- MinIO: `mc mirror` or volume copy fallback
- 30-day retention with automatic cleanup

### Alembic Migrations
29 numbered migrations (0001–0028) plus the health-snapshot revision, covering:
1. Initial schema (all core tables)
2. Append-only enforcement (triggers on consent_ledger, audit_logs)
3. Webhook URL column on users
4. Composite indexes for query performance
5. Subject annotations junction table
6. Drop consent_ledger updated_at (append-only consistency)
7. Quotes table
8. Monetary float → decimal
9. Studio tables (sessions, actions)
10. Phase 7 assignment + ingest extensions
11–14. Road/agri annotations, training jobs, deployed models, image records
15–19. Schema drift fixes, experiment events, user settings, workspace settings

Run: `cd edgevision-mw && alembic upgrade head`

---

## 10. Testing

### Test Framework
- pytest + pytest-asyncio
- HTTPX `AsyncClient` with `ASGITransport` for async endpoint testing
- Real PostgreSQL database (not mocked) via shared engine

### Key Fixtures (tests/conftest.py)
- `db_session` — Async session in an outer transaction that rolls back after each test (no cross-file DB pollution)
- `db_session_factory` — Standalone async sessionmaker + engine (for tests that commit data read by app code on a separate connection)
- `test_client` — FastAPI test client with DB override and rate limits bypassed
- `rate_limit_client` — Test client with real Redis-backed rate limits (for `test_rate_limit.py` only)
- `jwt_token_factory` — Mints JWT tokens; tests hitting FK-protected endpoints must create a `User` row first
- `api_key_factory` — Generates raw + hashed API keys
- `node_keypair_factory` — Generates Ed25519 key pairs
- `mock_minio` — MagicMock MinIO client
- `_clear_rate_limiter` / `_flush_rate_limit_redis` — Auto-use fixtures flushing in-memory and Redis rate-limit keys
- `_reset_app_db_engine` — Auto-use fixture calling `engine.dispose()` after each test (prevents asyncpg loop bleed)

### Test Files
- `test_fleet.py` — Heartbeat, fleet status, alerts, telemetry, commands
- `test_ingestion.py` — Batch upload, validation, queue stats, checksum verification
- `test_annotation.py` — Assignment, label submission, QA review, IAA calculation, leaderboard
- `test_catalog.py` — Dataset search, build, manifest, quotes, pricing
- `test_compliance.py` — Consent record/withdraw/verify, PII audit, daily audit
- `test_billing.py` — Export initiation, payment escrow, delivery confirmation
- `test_auth.py` — Registration, login, API keys, /me
- `test_rate_limit.py` — Rate limiting behavior
- `test_buyer_notification.py` — Webhook notification with retry
- `test_health.py` — Health check endpoint
- `test_metrics.py` — Prometheus metrics endpoint
- `test_analytics.py` — Analytics queries
- `test_studio.py` — Annotation studio sessions
- `test_studio_ai.py` — AI-assisted annotation
- `test_studio_review.py` — Studio review workflow
- `test_studio_sync.py` — Studio sync operations
- `test_studio_datasets.py` — Studio dataset management
- `test_studio_intelligence.py` — Dataset health, class distribution, dedup analysis
- `test_annotations_live.py` — Live annotation endpoints
- `test_live_annotation.py` — Live annotation service
- `test_live_annotation_ws.py` — WebSocket annotation
- `test_review_live.py` — Live review workflow
- `test_prelabel.py` — Pre-labeling pipeline
- `test_agri.py` — Agriculture analysis endpoints
- `test_road_scene_api.py` — Road scene analysis
- `test_road_semantic.py` — Road semantic segmentation
- `test_road_segmenter.py` — Road segmentation model
- `test_object_tracker.py` — Object tracking
- `test_locate_anything.py` — Locate-anything query
- `test_phase7.py` — Phase 7 features
- `test_phase1_gap_coverage.py` — Phase 1 gap coverage tests
- `test_batch_inference.py` — Batch inference pipeline
- `test_image_upload.py` — Image upload endpoints
- `test_video_upload.py` — Video upload endpoints
- `test_video_processing.py` — Video processing pipeline
- `test_upload_pipeline.py` — End-to-end upload pipeline
- `test_export_builder.py` — Export build process
- `test_dataset_pipeline.py` — Dataset build pipeline
- `test_operator_api.py` — Operator endpoints
- `test_buyer_dashboard.py` — Buyer dashboard endpoints
- `test_subject_portal.py` — Subject portal endpoints
- `test_alerts_api.py` — Alerts API endpoints
- `test_perception_events_api.py` — Perception events API
- `test_events.py` — Event system
- `test_openapi.py` — OpenAPI schema validation
- `test_security_headers.py` — Security header checks
- `test_pagination.py` — Pagination behavior
- `test_dedup.py` — Deduplication analysis
- `test_pii_redaction.py` — PII redaction
- `test_ws_metrics.py` — WebSocket metrics
- `test_live_inference_masks.py` — Live inference mask generation
- `test_live_label_bridge.py` — Live label bridge
- `test_sam_segmenter.py` — SAM segmentation
- `test_yolo_seg.py` — YOLO segmentation
- `test_clip_embed.py` — CLIP embedding
- `test_mask_utils.py` — Mask utility functions
- `test_depth_estimator.py` — Depth estimation
- `test_metric_depth.py` — Metric depth
- `test_mono_3d.py` — Monocular 3D detection
- `test_api_key_hashing.py` — API key hashing
- `schemas/test_geometry.py` — GeoPoint validation, bbox validation
- `schemas/test_annotation_schema.py` — Annotation schema validation

---

## 11. Code Conventions & Patterns

### Naming
- Models: PascalCase singular (`Node`, `IngestionBatch`, `AuditLog`)
- Tables: lowercase plural (`nodes`, `ingestion_batches`, `audit_logs`)
- Enums: PascalCase class, UPPER_SNAKE_CASE values
- API routes: kebab-case (`/ingest/batch`, `/consent/withdraw`)
- Variables/functions: snake_case

### Async Pattern
- All database operations use `AsyncSession` with `await db.execute()`, `await db.commit()`
- Services are async functions accepting `db: AsyncSession`
- API endpoints are async, using `Depends()` for auth and DB injection
- Celery tasks bridge sync→async via `asyncio.run()`

### Error Handling
- Services raise `ValueError` for business logic errors
- API layer catches and converts to `HTTPException` with appropriate status codes
- Custom `AppError` hierarchy for structured error responses
- Validation errors return 422 with field-level details

### Pydantic Conventions
- `model_config = ConfigDict(from_attributes=True)` on all schemas
- `Field(...)` with `description` on all fields
- `field_validator` and `model_validator` for custom validation
- Separate Request/Response schemas (e.g., `QuoteRequest` / `QuoteResponse`)

### SQLAlchemy Conventions
- `Mapped[type]` with `mapped_column()` (2.0 style)
- `JSONB` for flexible structured data
- `ARRAY(String)` for string arrays
- `UUID(as_uuid=True)` primary keys with `uuid.uuid4` default
- `ForeignKey` with `ondelete` specified
- Indexes on frequently queried columns

---

## 12. Known Issues & Improvement Opportunities

### Critical
1. **Hardcoded credentials in `config.py` defaults** — `edgevision_secret`, `minioadmin` should have no defaults in production

### High Priority
2. **Missing database indexes** — Some composite indexes still missing on high-traffic tables
3. **`/exports` list endpoint** — RESOLVED: fully implemented for buyers
4. **`/exports/{export_id}` endpoint** — RESOLVED: connected to actual export data
5. **Invoice/receipt generation** — PARTIALLY RESOLVED: export lifecycle is complete but formal invoice PDF not yet generated
6. **Buyer/marketplace UI missing** — Consent, catalog, quotes, billing, and exports have backends but limited frontend screens

### Medium Priority
7. **N+1 query in `get_leaderboard()`** — Should use JOIN
8. **`calculate_iaa` IoU is unidirectional** — Only matches A→B, not B→A
9. **No pagination on `/nodes/` and `/nodes/alerts`**
10. **No rate limiting on `/consent/withdraw`**
11. **Webhook notification only logs failure, doesn't queue for retry**
12. **MobileSAM decoder ONNX export is defective** — YOLOv8-seg is the primary mask backend; SAM falls back to heuristics when probe fails

### Resolved / Updated (Aug 2026)
- **`pyproject.toml`, `README.md`, `LICENSE`, `CONTRIBUTING.md`** — Present in `edgevision-mw/`
- **`init_db()` `create_all`** — Removed; schema managed by Alembic only
- **Prometheus metrics** — `app/api/metrics.py` exposes `/metrics`
- **Celery beat schedule** — Defined in `app/workers/celery_app.py`
- **Test isolation** — `conftest.py` uses per-test transaction rollback, Redis key flush, and app-engine dispose between tests
- **Git** — Repository initialized at workspace root

### Architecture Suggestions
29. **Separate read/write models** — Consider CQRS for high-read endpoints like fleet status
30. **Event sourcing for consent** — The append-only pattern is already in place; formalize with event store
31. **API versioning strategy** — Currently `/api/v1` but no version negotiation or deprecation headers
32. **Background job for consent expiry** — Currently no task auto-expires consents past their `expiry` date
33. **Auto-label E2E against real MinIO** — Unit tests mock MinIO; full path needs Docker stack + ONNX weights in `models/` + a batch with objects in the bucket
34. **MinIO lifecycle policies** — No automatic tiering or deletion of raw data after processing

---

## 13. Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Set to `production` for JSON logging |
| `POSTGRES_USER` | `edgevision` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `edgevision_secret` | PostgreSQL password |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `edgevision_mw` | PostgreSQL database name |
| `DATABASE_URL` | (auto-built) | Full async PostgreSQL URL |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `REDIS_PASSWORD` | `edgevision_redis` | Redis password |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `edgevision-data-lake` | MinIO bucket name |
| `MINIO_SECURE` | `false` | Use TLS for MinIO |
| `SECRET_KEY` | (required) | JWT signing key |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token expiry |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker |
| `NODE_HEARTBEAT_INTERVAL` | `30` | Expected heartbeat interval (seconds) |
| `ANNOTATION_TARGET_IAA` | `0.96` | Minimum IAA for certification |
| `MINIMUM_ANNOTATOR_WAGE_MWK` | `5000.0` | Minimum daily wage (Malawian Kwacha) |
| `MWK_TO_USD_RATE` | `0.0006` | MWK to USD conversion |
| `CORS_ORIGINS` | `""` | Comma-separated allowed origins |

---

## 14. Quick Start Commands

```bash
# Setup
cp .env.example .env
# Edit .env with secure values

# Start all services
docker compose up -d

# Run migrations
docker compose exec app alembic upgrade head

# Create admin user
docker compose exec app python -c "
from app.core.database import async_session
from app.auth.service import create_user
import asyncio
asyncio.run(create_user(await async_session().__aenter__(), {
    'email': 'admin@edgevision.mw', 'password': 'changeme',
    'full_name': 'Admin User', 'role': 'ADMIN'
}))
"

# Run tests
docker compose exec app pytest tests/ -v

# View API docs
open http://localhost:8000/docs

# Backup
./scripts/backup.sh /mnt/backups

# Check health
curl http://localhost:8000/health

# Production activation (run in order)
POSTGRES_HOST=localhost python scripts/activation/register_node.py      # P1.1
POSTGRES_HOST=localhost python scripts/activation/daily_check.py        # Daily discipline
POSTGRES_HOST=localhost python scripts/activation/process_batch.py --frames /path/to/frames --node LIL-TRUST-001  # P1.2
POSTGRES_HOST=localhost python scripts/activation/validate_yolo.py --frames /path/to/frames --model yolov8x.pt    # P2.1
POSTGRES_HOST=localhost python scripts/activation/generate_report.py --node LIL-TRUST-001 --days 7                 # P4.1
```

---

## 15. Data Flow Summary

```
Edge Node (capture)
  │
  ▼
Heartbeat (POST /nodes/heartbeat) ──→ Node status update + alerts
  │
  ▼
Ingestion Batch (POST /ingest/batch)
  │ ├── Checksum verification
  │ ├── Ed25519 signature verification
  │ ├── MinIO storage
  │ └── Idempotency check
  │
  ▼
Auto-Labeling (Celery: workers.auto_label)
  │ ├── MinIO fetch → YOLO prelabel → YOLOv8-seg masks (SAM if decoder probe OK)
  │ └── Batch → INGESTED; one Annotation row per image
  │
  ▼
Annotations created (one per image in batch)
  │
  ▼
Job Assignment (POST /jobs/assign)
  │ └── Workload-balanced round-robin with SELECT FOR UPDATE
  │
  ▼
Human Labeling (POST /jobs/{id}/submit)
  │ └── ANNOTATOR submits labels → QA_REVIEW
  │
  ▼
QA Review (POST /jobs/{id}/review)
  │ ├── Server-side IAA calculation (IoU or Cohen's Kappa)
  │ ├── IAA ≥ 0.96 → CERTIFIED
  │ └── IAA < 0.96 → REJECTED
  │
  ▼
Dataset Build (POST /datasets/build → Celery)
  │ ├── Stratified sampling + class balancing
  │ ├── PII check
  │ ├── Consent coverage verification
  │ └── Price calculation
  │
  ▼
Quote Generation (POST /datasets/quotes)
  │ └── Base × exclusivity × geography premium
  │
  ▼
Export (POST /exports)
  │ ├── DPA verification
  │ ├── Credit escrow
  │ ├── License key generation
  │ └── Celery: watermarking + secure transfer
  │
  ▼
Delivery Confirmation (POST /webhooks/buyer)
  │ └── Export COMPLETED + audit log
  │
  ▼
Buyer Notification (webhook retry with audit)
```
