# EdgeVision Studio — Phase 4+ Status Report

**Date:** 27 July 2026
**Author:** opencode (automated)
**Test Status:** 145/145 passing | **Backend:** running locally on :8000 | **Frontend:** Vite dev on :3000

---

## Executive Summary

EdgeVision Studio has been built across 5 phases (Phase 1–4 + hotfixes). The system is a **functional prototype** with a working backend, AI-assisted annotation frontend, and four ONNX models deployed in-browser. However, it is **not production-ready**. Significant gaps remain between what the code _implements_ and what a real annotation workflow _requires_. This report is an honest accounting.

---

## What Actually Works (Verified)

### Backend API — Solid Foundation
| Component | Status | Detail |
|-----------|--------|--------|
| Auth (JWT + register/login) | **Working** | Admin user `admin@edgevision.mw` created and tested |
| Session CRUD | **Working** | Creates annotation sessions from string dataset IDs (e.g. `DS-LILONGWE-001`) |
| Image listing | **Working** | Returns paginated image lists from the `annotations` table |
| Annotation save | **Working** | Saves bounding boxes with label + tool metadata |
| Health score | **Working** | Computes completeness/accuracy/consistency from actual data |
| Image serving | **Stub** | Attempts MinIO fetch; returns 503 when MinIO unavailable (which is always in local dev) |
| Batch sync (Phase 4) | **Working** | ETag-based conflict resolution for create/edit/delete/approve/reject |
| Export creation | **Working** | Creates export jobs in DB |
| Export delivery | **Stub** | Jobs are created but never actually built or delivered |
| Dedup analysis | **Stub** | Celery task dispatched but `studio.dedup_analyze` not registered in workers |
| Export build | **Stub** | Celery task dispatched but `studio.export_build` not registered in workers |

### Frontend UI — Polished Shell
| Component | Status | Detail |
|-----------|--------|--------|
| Login page | **Working** | Gradient design, form validation, error handling, loading state |
| Home/dashboard | **Working** | Session creation via string ID, health grid, quick-action cards |
| Navigation | **Working** | Persistent top nav bar, tab switching, brand logo returns home |
| Image sidebar | **Working** | Loads thumbnails from API, highlights current, shows label progress |
| Annotation canvas | **Working** | Fabric.js v6 bbox drawing, label assignment, color coding |
| Health dashboard | **Working** | Recharts-based score cards, class distribution pie chart |
| Dedup panel | **UI renders** | Calls API, shows placeholder UI; backend dedup Celery task not wired |
| Export preview | **UI renders** | Calls API, shows format selector; actual export never completes |
| TurboReview | **UI exists** | Keyboard-driven batch review component; references APIs that don't exist |
| LabelCanvas (Phase 2) | **UI exists** | AI toolbar, polygon tool; imports `useExperiment` from A/B test config (stub) |
| VirtualImageList | **UI exists** | Virtualized scrolling component; not connected to main flow |
| Offline sync indicator | **Working** | Shows online/offline status, pending count, sync button |
| Touch canvas hooks | **Built** | Pinch/pan/stylus pressure handling; no touch device to test on |
| i18n (Chichewa) | **Built** | 200+ keys for English + Chichewa; not wired into all components |

### ONNX Models — Real, But Untested in Practice
| Model | Size | Purpose | Actually Used? |
|-------|------|---------|----------------|
| YOLOv8n-cls | 5.2 MB | Image classification | Loaded by `useAIAssist` hook; inference path exists but never tested end-to-end |
| MobileSAM encoder | 27 MB | Segment Anything encoding | Loaded; encoder runs on image data |
| MobileSAM decoder | 20 MB | Click-to-segment | Loaded; decoder takes click point + embedding → mask |
| CLIP ViT-B/32 | 335 MB | Semantic similarity | Registered; not called from any component |

Total model payload: **387 MB** downloaded to browser on first use.

### Infrastructure
| Service | Status | Detail |
|---------|--------|--------|
| PostgreSQL 16 + pgvector | **Running** | Docker, localhost:5432, 22 tables |
| Redis 7 | **Running** | Docker, localhost:6379 |
| MinIO | **Running** | Docker, localhost:9000/9001 — **but backend can't reach it in local dev mode** |
| Celery worker | **Running** | Docker, but `studio.*` tasks not registered |
| Celery beat | **Running** | Docker, no periodic tasks configured |
| Alembic migrations | **7 migrations** | Covering initial schema through quotes table |

### Test Suite
| Suite | Count | Notes |
|-------|-------|-------|
| Core API (fleet, ingestion, annotation, catalog, compliance, billing, auth) | 104 | All passing |
| Studio Phase 1 | 13 | Session, annotation, image, health, export endpoints |
| Studio AI-assist | 5 | Session creation, image listing, annotation save |
| Studio Phase 3 (intelligence) | 11 | Health score, dedup, export preview/build |
| Studio Phase 4 (sync) | 12 | Batch sync, conflict resolution, status |
| **Total** | **145** | **All passing** |

---

## What's Broken or Missing

### Critical Gaps

1. **No real images.** The annotation canvas tries to fetch images from MinIO via `/api/v1/studio/images/{id}/serve`. MinIO is running but the backend runs locally with `POSTGRES_HOST=localhost` while MinIO expects Docker networking. The 20 test annotations have paths like `images/0000.jpg` that don't exist in MinIO. **The canvas will always show a broken image.**

2. **Celery tasks are stubs.** The workers register generic tasks (`workers.process_batch`, `workers.build_dataset`, etc.) but not `studio.dedup_analyze` or `studio.export_build`. The dedup and export intelligence endpoints dispatch these tasks, but they silently fail. Celery beat has no schedule defined.

3. **Backend/MinIO disconnect.** When running locally (not in Docker), the backend can't reach MinIO (`minio:9000`). Image serving returns 503. This means the entire annotation workflow — load image → draw boxes → save — can't be visually verified.

4. **No image ingestion pipeline.** There's no way to upload images through the UI or API into MinIO and create annotation records. The 20 test records were created manually via test fixtures. A real workflow needs: upload images → create annotations → assign to annotators.

### Functional Gaps

5. **TurboReview references non-existent APIs.** It calls `/studio/sessions/{id}/review/batch` which doesn't exist in any backend router.

6. **LabelCanvas imports `useExperiment` from A/B test config.** The file exists (`frontend/src/experiments/abTestConfig.ts`) but is a stub. This would cause a runtime error if LabelCanvas were rendered.

7. **Export is fire-and-forget.** `POST /studio/exports` creates a job record, but nothing processes it. There's no download URL, no file generation, no COCO/YOLO manifest building.

8. **Dedup is UI-only.** The `DedupPanel` component renders analysis options and calls the API, but the backend task never runs. No duplicate groups are ever created.

9. **Service worker caching is configured but untested.** Workbox config in vite.config.ts sets up API and image caching strategies, but without real images flowing through the system, this is unverified.

10. **Offline sync writes to IndexedDB but the sync endpoint needs a real session.** `useOfflineSync` queues actions to Dexie, but the `POST /studio/sync/batch` endpoint requires valid annotation IDs that don't exist in a demo scenario.

### Design Gaps

11. **No dataset management UI.** Users must know their dataset ID string. There's no browse, search, or create-dataset interface.

12. **No annotator assignment workflow.** Sessions are created but there's no job queue, no assignment, no deadline tracking in the UI.

13. **No QA review flow.** The backend has IAA calculation and certification logic, but the UI has no QA review screen. TurboReview exists as a component but isn't wired into the main flow.

14. **No user management.** No way to create annotators, assign roles, or view team activity from the UI.

15. **Chichewa i18n incomplete.** The locale files exist with ~200 keys each, but most components use hardcoded English strings. Only the offline badge uses `t()`.

---

## Architecture Reality Check

### What We Built vs. What We Claimed

| Claimed | Reality |
|---------|---------|
| "AI-powered annotation platform" | Canvas draws rectangles. ONNX models load but inference is untested on real images. |
| "Click-to-segment with MobileSAM" | Code path exists: click → encode → decode → mask. Never tested with real image data flowing through. |
| "Offline-first with background sync" | IndexedDB queue writes successfully. Sync endpoint exists. But no offline images cached, so offline mode is meaningless. |
| "Turbo Review for batch QA" | Component renders. Keyboard shortcuts registered. But references non-existent API. |
| "4 ONNX models exported and deployed" | Files exist in `public/models/` (387 MB total). Loading logic works. Inference pipelines coded. Untested end-to-end. |
| "145 tests passing" | True. But tests verify API contracts and data flow, not visual correctness or real image processing. |
| "Chichewa localization" | Translation files exist. Only 2-3 strings in the UI actually use the `t()` function. |

### Code Volume vs. Code Quality

- **67 backend Python files** — Most are well-structured, async, with proper error handling. The core API (auth, fleet, ingestion, annotation, catalog, compliance, billing) is production-grade.
- **24 frontend TypeScript files** — Mix of working components (login, home, annotation, sidebar) and scaffolding (TurboReview, LabelCanvas, VirtualImageList, Phase 3/4 components). Some import paths reference modules that exist but have stub implementations.
- **18 test files** — Comprehensive coverage of API contracts. No visual/E2E tests. No Playwright, Cypress, or screenshot tests.
- **4 ONNX models** — Real exports from PyTorch. The CLIP model alone is 335 MB. Loading this in a browser tab on a Malawian edge device with limited bandwidth is questionable.

---

## What's Running Right Now

```
http://localhost:3000  → Vite dev server (frontend)
http://localhost:8000  → Uvicorn with --reload (backend, local)
localhost:5432         → PostgreSQL 16 (Docker)
localhost:6379         → Redis 7 (Docker)
localhost:9000/9001    → MinIO (Docker, unreachable from local backend)
```

**User flow that works:** Login → enter dataset ID `DS-LILONGWE-001` → session created → annotation view loads → canvas appears (but image is broken) → draw bounding boxes → save (succeeds) → health dashboard shows stats.

**User flow that doesn't work:** See actual images → run AI assist → batch review → dedup analysis → export dataset → work offline.

---

## Honest Assessment

### What This Is
A **well-architected prototype** demonstrating the full stack of an annotation platform: FastAPI backend with 22 database tables, React frontend with Fabric.js canvas, ONNX model integration, offline sync infrastructure, and multi-phase development methodology. The code quality is high. The test coverage is thorough. The architecture is sound.

### What This Isn't
A **production-ready annotation tool**. It can't process real images. It can't run AI inference on actual data. It can't export datasets. A human annotator cannot sit down and start labeling images with this tool today. The offline mode, Turbo Review, dedup, and export features are structural implementations — the plumbing is there, but the water doesn't flow.

### The Gap
The distance between "the API returns annotation data" and "an annotator draws a box on a real image and it saves correctly" is the MinIO connectivity gap. The distance between "ONNX models load in the browser" and "clicking on a car produces a segmentation mask" is the image-pipeline gap. Both are solvable but require real images in MinIO and end-to-end integration testing.

---

## Recommended Next Steps (Prioritized)

1. **Seed MinIO with real images** — Upload 20-50 test images from the Lilongwe dataset into MinIO, create matching annotation records. This unblocks the entire visual workflow.

2. **Fix MinIO connectivity for local dev** — Either run the backend in Docker (with volume mounts for hot reload) or configure local backend to reach `localhost:9000` instead of `minio:9000`.

3. **Wire up Celery tasks** — Register `studio.dedup_analyze` and `studio.export_build` in the worker so the intelligence features actually execute.

4. **End-to-end integration test** — Login → create session → see image → draw box → save → verify in DB → export. This is the critical path.

5. **Test ONNX inference on real images** — Verify that MobileSAM click-to-segment actually produces reasonable masks on real Lilongwe imagery.

6. **Remove or fix broken components** — TurboReview's non-existent API calls, LabelCanvas's A/B test import, and VirtualImageList's disconnection should be fixed or removed to prevent runtime errors.
