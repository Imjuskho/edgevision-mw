# EdgeVision-MW — Phase 7 Development Prompt
## Image Ingestion, Annotator Assignment & QA Review

**Date:** 28 July 2026  
**Context:** EdgeVision-MW is a functional AI-powered annotation platform for Lilongwe road-user imagery. The backend is production-grade (145/145 tests passing). The frontend is polished with a full 85-class Malawi taxonomy, ONNX models deployed, and offline sync built. The system currently runs on localhost:3000 (frontend) and localhost:8000 (backend) with PostgreSQL, Redis, MinIO, and Celery in Docker.

**Current verified flow:** Login → Create Session (DS-LILONGWE-001) → Load 20 images → Draw bboxes on Fabric.js v6 canvas → Select from 85-class taxonomy → Save → Health Dashboard → Export COCO JSON.

---

## Goal

Close the operational gap between "code works in tests" and "an annotator can sit down and label real images in a managed workflow." Build the image ingestion pipeline, the annotator assignment system, and the QA review screen. These are the three highest-impact remaining features before field deployment.

---

## Phase 7 Scope (3 Workstreams)

### Workstream A: Image Ingestion Pipeline
**Problem:** Images must be uploaded to MinIO manually via `scripts/seed_minio.py`. There is no UI upload, no drag-and-drop, and no batch import from edge devices. Annotation records are created by hand.

**Deliverables:**
1. **Backend API endpoint** `POST /api/v1/ingest/images` — Accept multipart/form-data batch upload (up to 50 images, max 20 MB each). Validate file type (jpg/png/webp), generate SHA-256 checksum, upload to MinIO with structured path (`datasets/{dataset_id}/images/{uuid}.{ext}`), create `Annotation` records in PostgreSQL with `status=PENDING`, return batch metadata with upload progress.
2. **Dataset auto-creation** — If `dataset_id` doesn't exist, create it with `status=BUILDING`. Update to `READY` when first images uploaded.
3. **Duplicate detection at ingest** — Check SHA-256 against existing annotations. Reject exact duplicates with 409 Conflict; flag near-duplicates for review (use perceptual hash or CLIP embedding if available).
4. **Frontend drag-and-drop UI** — Add an "Upload Images" modal/page accessible from the Home dashboard. Features: drag-and-drop zone, file list with previews, progress bars, dataset selector (or create-new), upload button, error/success states, Chichewa i18n.
5. **Edge device import stub** — Add `POST /api/v1/ingest/batch` that accepts a JSON manifest + presigned MinIO URLs. This is the API contract for future edge-node uploads. Document the payload schema.

**Acceptance Criteria:**
- User can drag 20 images into the frontend, select/create a dataset, and click Upload.
- Images appear in MinIO console at `datasets/{id}/images/`.
- Annotation records are created with correct foreign keys.
- Duplicate image is rejected with clear error message.
- New dataset is auto-created if needed and transitions to READY.
- Endpoint returns 201 with batch summary (uploaded count, skipped count, dataset_id).

---

### Workstream B: Annotator Assignment Workflow
**Problem:** Sessions are created per-user with a raw dataset ID string. There is no job queue, no assignment logic exposed in the UI, no deadline tracking, and no workload balancing frontend. The backend has `workload-balanced round-robin` assignment logic but no frontend surface.

**Deliverables:**
1. **Backend assignment endpoints** — Formalize the existing assignment logic into explicit endpoints:
   - `POST /api/v1/jobs/assign` — Accept `dataset_id`, `annotator_ids[]`, `deadline`, `priority`. Creates annotation jobs, assigns images round-robin, returns job batch.
   - `GET /api/v1/jobs/queue` — For logged-in annotator, list their assigned jobs with status (PENDING / IN_PROGRESS / SUBMITTED / UNDER_REVIEW), deadline, and progress %.
   - `PATCH /api/v1/jobs/{job_id}/claim` — Annotator claims a PENDING job (locks to them, sets status=IN_PROGRESS).
   - `PATCH /api/v1/jobs/{job_id}/submit` — Annotator submits completed job (sets status=SUBMITTED, triggers IAA queue if applicable).
2. **Deadline & priority model** — Add `deadline` (datetime) and `priority` (int, default 0) to the job/session model. Update Alembic migration.
3. **Annotator dashboard** — New frontend route `/queue` showing:
   - My Jobs table (sortable by deadline, priority, status)
   - Claim button for available jobs
   - Progress bar per job (% of images annotated)
   - Overdue badge (red if past deadline)
   - Quick-start button to open AnnotationPage for the selected job
4. **Admin assignment UI** — New frontend route `/admin/assign` (admin role only) showing:
   - Dataset selector
   - Annotator multi-select (list users with role=annotator)
   - Deadline picker, priority slider
   - Workload preview ("Alice: 150 images, Bob: 150 images")
   - Assign button + confirmation

**Acceptance Criteria:**
- Admin can assign a dataset to 2 annotators with a deadline.
- Annotator logs in, sees their job queue, claims a job.
- Annotator opens the job → AnnotationPage loads with only the assigned images.
- Annotator draws boxes, saves, progress bar updates.
- Annotator submits job → status changes to SUBMITTED.
- Admin sees submission in a review queue (stub for Phase 7; full QA in Workstream C).
- All endpoints protected by role-based JWT auth.

---

### Workstream C: QA Review Screen
**Problem:** The backend has IAA calculation (IoU + Cohen's Kappa) and certification logic. The `TurboReview` component exists with keyboard shortcuts but is not wired into the main annotation flow as a screen. There is no "annotator submits → QA reviews → certified/rejected" loop.

**Deliverables:**
1. **Backend QA endpoints** (formalize what's partially there):
   - `GET /api/v1/review/queue` — List all SUBMITTED jobs awaiting review, with annotator name, dataset name, annotation count, IAA score preview.
   - `GET /api/v1/review/jobs/{job_id}` — Detail view with all annotations, images, and sidebar for navigation.
   - `POST /api/v1/review/jobs/{job_id}/certify` — Mark job CERTIFIED. Trigger IAA calculation against gold standard if available. Update annotator stats.
   - `POST /api/v1/review/jobs/{job_id}/reject` — Mark job REJECTED with `rejection_reason`. Return to annotator queue as PENDING.
   - `GET /api/v1/review/jobs/{job_id}/iaa` — Return IAA metrics (per-class IoU, Cohen's Kappa, sample-level agreement).
2. **TurboReview integration** — Wire the existing `TurboReview` component into a new route `/review/:jobId`. It should:
   - Load job details from the new QA endpoints.
   - Display images in a filmstrip sidebar.
   - Render annotations as overlays on the canvas (read-only mode with approve/reject per-annotation).
   - Support keyboard shortcuts: `A` = approve all, `R` = reject all, `→` / `←` = next/prev image, `1-9` = toggle annotation approval.
   - Show IAA score card in the header.
   - Final actions: "Certify" (green) or "Reject with reason" (red modal).
3. **Submission flow hook** — When annotator clicks "Submit Job" in AnnotationPage:
   - Confirm dialog: "Submit 45/50 images? You cannot edit after submission."
   - Call `POST /api/v1/jobs/{job_id}/submit`.
   - Redirect to queue with success toast.
   - Job appears in QA review queue within 1 second (no page refresh needed for admin).

**Acceptance Criteria:**
- Annotator submits a job → it disappears from their queue and appears in QA review queue.
- QA reviewer opens `/review/{job_id}` → sees all images with annotations overlaid.
- Reviewer approves/rejects individual annotations with keyboard shortcuts.
- Reviewer clicks "Certify" → job status = CERTIFIED, annotator sees it in their history.
- Reviewer clicks "Reject" → job returns to annotator queue with rejection reason.
- IAA endpoint returns meaningful numbers (not NaN) when gold-standard data exists.

---

## Technical Constraints

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, MinIO (boto3), PostgreSQL 16, Redis 7, Celery.
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Fabric.js v6, Recharts, Dexie (IndexedDB), react-i18next.
- **Auth:** JWT with role claims (`admin`, `annotator`, `qa`, `viewer`). Use existing `@require_role` dependency.
- **File storage:** MinIO via `app/core/minio_client.py`. Use existing `upload_file`, `get_presigned_url` helpers.
- **Tests:** Add pytest coverage for all new endpoints. Target: +30 tests, all passing. Maintain 145 existing tests.
- **i18n:** All new UI text must use `t()` and be added to both `en.json` and `ny.json`.
- **No breaking changes:** Existing login flow, annotation canvas, taxonomy, and export pipeline must remain intact.

---

## Suggested File Touch Points

### Backend
- `app/api/ingest.py` — extend with batch image upload
- `app/api/jobs.py` — new assignment endpoints (or expand existing annotation router)
- `app/api/review.py` — new QA review router
- `app/models/` — add deadline/priority to job/session models, new migration
- `app/schemas/` — Pydantic schemas for upload, assignment, review payloads
- `app/services/assignment.py` — round-robin logic extracted from inline code
- `tests/test_ingest_images.py`, `tests/test_assignment.py`, `tests/test_review.py`

### Frontend
- `frontend/src/pages/UploadPage.tsx` — drag-and-drop upload
- `frontend/src/pages/QueuePage.tsx` — annotator job queue
- `frontend/src/pages/AdminAssignPage.tsx` — admin assignment UI
- `frontend/src/pages/ReviewPage.tsx` — QA review wrapper for TurboReview
- `frontend/src/components/TurboReview.tsx` — wire to real API, add read-only canvas overlay
- `frontend/src/App.tsx` — add routes `/upload`, `/queue`, `/admin/assign`, `/review/:jobId`
- `frontend/src/api/` — new API wrappers for ingest, assignment, review endpoints
- `frontend/src/i18n/locales/en.json` + `ny.json` — new keys

---

## Definition of Done for Phase 7

- [ ] Image ingestion API handles 50-image batch upload with dedup
- [ ] Frontend drag-and-drop upload page is functional and translated
- [ ] Annotator can claim, work, and submit a job through the UI
- [ ] Admin can assign jobs to annotators with deadlines
- [ ] QA reviewer can certify or reject a submitted job via TurboReview
- [ ] All new endpoints have passing tests (+30 tests, 175/175 total)
- [ ] No regressions in existing 145 tests
- [ ] All new UI strings are i18n-ready (en + ny)
- [ ] README or docs updated with new endpoints and user flows

---

## Out of Scope (Future Phases)

- Server-side pre-labeling with YOLO/SAM (Phase 8)
- CLIP semantic dedup wiring (Phase 8)
- Offline image caching in IndexedDB (Phase 10)
- CI/CD pipeline (Phase 9)
- Prometheus monitoring (Phase 9)
- Docker rebuild for Celery worker with studio.* tasks (Phase 9)
- Data marketplace / buyer catalog (Phase 10+)

---

## Reference Docs

- `docs/PROGRESS_REPORT.md` — Full system status and architecture inventory
- `docs/malawi-road-user-taxonomy.md` — 85-class taxonomy reference
- `docs/annotator-onboarding-guide.md` — Intended end-user workflow
- `docs/smoke-test.md` — Manual test script to re-run after Phase 7

