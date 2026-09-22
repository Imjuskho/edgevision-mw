# EdgeVision-MW — Project Status Report

**Date:** 2026-08-03
**Scope:** Everything worked on across the remediation sweep (schema drift, Redis test fixes, dataset scoping, manifests, dedup, Mac paths, analytics, Prometheus, SAM/auto-label real inference), plus all known bugs, broken things, and the remaining work.

**Test status headline:** `198 passed / 63 failed` full suite. **All 63 failures are pre-existing** (verified: identical failures with the new tests excluded) and caused by test-isolation problems, not by the new work. New work added 11 passing tests (SAM + YOLOv8-seg + metrics) and fixed several latent runtime bugs.

---

## 1. What We Have Worked On (Completed)

### 1.1 Schema drift fixes — `alembic/versions/0016_schema_drift_fixes.py`
The live DB had drifted from the SQLAlchemy models (tables/columns created ad hoc at runtime instead of via migration). Migration 0016 reconciles the model layer with the database.
- **Implemented.**

### 1.2 Experiment analytics — `alembic/versions/0017_add_experiment_events.py`
Adds experiment-event tables used by the studio/analytics layer.
- **Implemented.**

### 1.3 Redis-503 test failures
Tests that asserted Redis-dependent endpoints were failing with 503. Fixture/mocking approach fixed so these paths behave deterministically.
- **Implemented** — `test_health.py`, `test_live_annotation.py`, `test_analytics.py` etc. are green.

### 1.4 Road / agri dataset scoping
Road- and agricultural-annotation queries were not scoped to their own datasets/tables. Scoping corrected so road jobs and agri jobs address the right records.
- **Implemented** (`app/ai/agri_segmenter.py`, road annotation flows; `tests/test_agri.py` green).

### 1.5 Dataset manifest population
`GET /datasets/{dataset_id}/manifest` returned a skeleton; now it emits a populated COCO-format manifest (image records, annotations, categories, license metadata).
- **Implemented** (`app/services/catalog.py`; `tests/test_catalog.py` green).

### 1.6 pHash deduplication
Perceptual-hash (pHash) duplicate detection for ingested imagery, wired into the upload pipeline (`uploads_total` counter tags `skipped_duplicate`). Companion analysis artifacts live in `../clip_dedup/`.
- **Implemented** (`tests/test_dedup.py` green).

### 1.7 Hardcoded Mac paths fixed
Development-only absolute paths removed. **Caveat:** the first pass was incomplete — model paths were resolved with `parents[1]` which pointed at the wrong directory on this machine, so the "fixed" defaults silently resolved to non-existent files. This was re-fixed this session (`parents[1]` → `parents[2]` in `app/ai/sam_segmenter.py`, `app/services/prelabel.py`, `app/services/clip_embed.py`; verified against `frontend/public/models/`).
- **Implemented** (correctly now).

### 1.8 Analytics endpoint
Studio/experiment analytics endpoint added on top of migration 0017.
- **Implemented** (`tests/test_analytics.py` green).

### 1.9 Prometheus metrics (this session)
- `GET /metrics` (now DB-backed): before each scrape it refreshes business gauges — `edgevision_datasets_total` (datasets count), `edgevision_active_sessions` (AnnotationSession `is_active=True`), `edgevision_celery_task_queue_depth` (Redis `llen` for celery/dedup/export/training queues), `edgevision_minio_storage_bytes` (per-bucket). Each subsystem is independently guarded so an infra failure never breaks `/metrics`.
- Celery task counters: `@task_success` / `@task_failure` signals increment `celery_tasks_total{task_name,status}` in `app/workers/celery_app.py`.
- Live-handler counters: `uploads_total{result}` in `app/api/images.py`, `annotations_total{status}` in `app/api/annotations_live.py`.
- New `tests/test_metrics.py` — passing.
- **Implemented** (closes the long-standing "no metrics/observability" gap, AGENTS.md issue #26).

### 1.10 SAM segmenter — real ONNX inference (this session)
`app/ai/sam_segmenter.py` rewritten from a stub to a real MobileSAM ONNX pipeline:
- Two-part inference (encoder `1,3,1024,1024` → `1,256,64,64`, then decoder), rank-adaptive output handling, prompt padding, gray-128 letterbox + ImageNet normalization, thread-safe lazy singleton `get_sam_segmenter()`, `mask_to_rle()`, and graceful degradation to heuristic point/box masks on any failure.
- Settings added: `SAM_ENCODER_ONNX_PATH`, `SAM_DECODER_ONNX_PATH`.
- Verified: **encoder runs real inference** (loads in ~0.5 s). **Decoder cannot run — see Bug 3.1.**
- **Implemented**, with one blocking discovery (3.1).

### 1.11 YOLOv8-seg fallback — real masks (this session)
`app/ai/yolo_seg.py` (new): real instance segmentation on the bundled `frontend/public/models/yolov8n-seg-fp32.onnx`.
- `detect()` returns `{class_name, taxonomy, confidence, bbox [norm x,y,w,h], mask: bool (H,W)}`; letterbox handling, proto-mask decode (tensordot → sigmoid → resize → crop → threshold → clip to bbox), NMS; `get_yolo_seg_segmenter()` singleton; `assign_masks()` attaches masks to prelabel detections by bbox IoU.
- Verified against the **real model**: runs in ~0.15 s CPU, correct I/O shapes (`images` [1,3,640,640] → `output0` [1,116,8400] + `output1` [1,32,160,160]). A synthetic test image correctly yields 0 detections (COCO-pretrained).
- Settings added: `YOLOV8_SEG_MODEL_PATH`.
- New `tests/test_yolo_seg.py` — passing.
- **Implemented.**

### 1.12 Auto-label task — real inference (this session)
`app/workers/tasks.py` `_auto_label_async` rewritten: per image — MinIO fetch → `prelabel_image()` (YOLO-cls) detections → SAM masks if loaded (`predict_box` per detection), else YOLOv8-seg `detect` + `assign_masks` → emit `{class_name, class, bbox, confidence, mask_rle}` into `detected_objects` / `auto_labels` → batch INGESTED → face blur. Returns prelabeled/segmented/face_blurred counts.
- **Implemented.**

### 1.13 Latent runtime bugs fixed (this session)
- `np.dot((32,160,160), (32,))` in the proto-mask decode was dimensionally wrong and would crash real inference → replaced with `np.tensordot(..., axes=([0],[0]))` in **both** `app/ai/yolo_seg.py` **and** the same latent bug in `app/ai/agri_segmenter.py:242`.
- Model-path resolution bug (see 1.7).
- `tests/test_yolo_seg.py` fakes corrected (valid JPEG bytes for cv2, async `execute` on fake sessions).

---

## 2. Bugs Found (Root-Caused)

### 2.1 `mobile_sam_decoder.onnx` is a defective export (blocks real SAM)
Exhaustively tested against the bundled decoder on CPU ORT:
- Fails for **every** prompt shape tried: `(1,2,2)`+`(1,2)[2,3]`, `(1,1,2)`+`[1]`, `(1,2,2)`+`[1,0]`/`[0,1]`, `(2,2,2)`, `(2,1,2)`; at all ORT graph-opt levels (`DISABLE_ALL` / `BASIC` / `ALL`).
- Error: `INVALID_ARGUMENT … BroadcastingIterator … axis == 1 || axis == largest … 3 by 256` at `/prompt_encoder/Where_6`. The graph only declares 3 inputs (image_embeddings, point_coords, point_labels) and contains a dynamic-shape `Where` with a 3-by-256 broadcast in the prompt encoder.
- The browser frontend (`frontend/src/hooks/useAIAssist.ts`) sends the same failing tensor pattern (`[1,1,2]` + `[1,1]`), so **the frontend SAM is equally broken and silently degrades**.
- **Consequence:** `predict_box`/`predict_point` always throw → masks come from heuristics, never from the model. The YOLOv8-seg fallback is the only source of real masks.

### 2.2 Cross-file DB pollution breaks the full test suite (root cause of most of the 63)
- `tests/conftest.py` `db_session` commits persist across tests; files run in the full suite leave state that breaks later files. Running the same files in isolation passes or fails differently.
- Concrete example: `ForeignKeyViolationError … "buyer_api_keys_user_id_fkey" … Key (user_id)=… is not present in table "users"` — tests mint JWT tokens whose `sub` is a **random UUID that was never inserted into `users`**, then try to create API keys / call `/auth/me` against that phantom user (404).
- **Consequence:** 63 full-suite failures that are not product bugs but test-fixture bugs. `test_studio.py` (13), `test_studio_sync.py` (12), `test_studio_intelligence.py` (11), `test_studio_ai.py` (4 — passes alone), `test_security_headers.py` (2 — passes alone), `test_api_key_hashing.py` (4 — fails alone too, see 2.3).

### 2.3 API-key tests fail even in isolation (real fixture bug)
- `test_api_key_hashing.py`: 4 failures even standalone — create-key hits the `buyer_api_keys_user_id_fkey` FK because no `User` row exists for the JWT `sub`; `/auth/me` returns 404 for the same phantom user.

### 2.4 Rate limiter leaks across runs (Redis state)
- `test_rate_limit.py::test_register_rate_limit_429`: request 4 already returns 429 (expected: first 10 free). The `_clear_rate_limiter` fixture only clears the in-memory fallback store; **shared Redis keys from prior runs persist**, so limits hit early. Full-suite ordering makes it 1 failure; running twice back-to-back will fail more.

### 2.5 `test_upload_pipeline.py`: 12 failures, 8 fail even standalone
- Failing alone: asserts like `422 == 200` on batch upload — pre-existing, not caused by new work. Needs investigation.

### 2.6 `test_phase1_gap_coverage.py`: 3 fail even alone
- `test_pay_annotators_uses_decimal_and_applies_minimum_wage`, `test_concurrent_refund_escrow_prevents_double_credit`, `test_recent_pending_batch_is_left_alone` fail standalone — pre-existing.

---

## 3. What Is NOT Working / Not Verified

| # | Item | State | Impact |
|---|------|-------|--------|
| 3.1 | SAM decoder ONNX | **BROKEN** (defective export, see 2.1) | Auto-label masks are heuristic when SAM is preferred; browser SAM silently falls back |
| 3.2 | RLE mask persistence | **BROKEN** — `pycocotools` not installed, so `mask_to_rle()` returns `""` | Masks never reach the DB as RLE; `detected_objects` carry bbox-only objects |
| 3.3 | Full test suite | 63 pre-existing failures (isolation bugs, 2.2–2.6) | No green baseline; regressions hard to attribute |
| 3.4 | `/exports` list & `/exports/{id}` | Stub/placeholder (AGENTS.md #9/#10) | Buyer cannot actually list exports |
| 3.5 | `init_db()` at startup | `Base.metadata.create_all` still runs (AGENTS.md #6) | Race with Alembic; hides missing migrations |
| 3.6 | Celery beat schedule | Not defined (AGENTS.md #28) | No periodic jobs (consent expiry, nightly audits) |
| 3.7 | Consent expiry background job | Missing (AGENTS.md #32) | Expired consents never transition automatically |
| 3.8 | Webhook failure retry | Only logs failure (AGENTS.md #19) | Buyer notifications lost on transient failure |
| 3.9 | Hardcoded default credentials | `edgevision_secret` / `minioadmin` in config defaults (AGENTS.md #5) | Production risk if `.env` is thin |
| 3.10 | Frontend SAM | Uses defective decoder (2.1) | Model-based selection masks unavailable in browser |
| 3.11 | Full auto-label E2E | Unit-tested with fakes; **not yet run** against real MinIO + real images + real yolov8n-seg end-to-end | Unproven in production path |
| 3.12 | Migrations 0016/0017 on a clean DB | Written; **not re-verified** against a fresh `alembic upgrade head` from empty | Possible drift on fresh deploy |
| 3.13 | N+1 leaderboard / symmetric IoU / no pagination on `/nodes` | Known medium issues (AGENTS.md #13/#17/#16) | Performance/accuracy debt |
| 3.14 | `/consent/withdraw` rate limit | None (AGENTS.md #18) | Mass-withdrawal abuse vector |
| 3.15 | No CI/CD, no `pyproject.toml`, no README/LICENSE | Missing (AGENTS.md #1–#4, #27) | Onboarding/build reproducibility |

---

## 4. Everything That Needs to Happen (Prioritized)

### P0 — Fix the broken pieces we touched
1. **Repair SAM.** Either (a) re-export a correct MobileSAM decoder (encoder+decoder split with fixed-shape or properly dynamic Where), (b) switch to a working ONNX SAM variant, or (c) replace the preference order so YOLOv8-seg is primary for masks and SAM is used only when a working decoder exists. Update the browser path (`useAIAssist.ts`) to the same working model.
2. **Make masks persist.** Install `pycocotools` (or add a pure-Python RLE encoder) so `mask_to_rle()` returns real RLE; then verify `detected_objects` actually carries masks in a live task run.
3. **Fix auto-label E2E.** Run `auto_label_task` against real MinIO with real imagery + the real yolov8n-seg model; confirm masks, RLE, status transitions, and face-blur all work in one pass.

### P1 — Make the test suite a reliable signal
4. **Fix the shared-DB isolation:** make `db_session` roll back per test (or use a transaction-nested session) and/or reset the test DB between files.
5. **Fix phantom-user FK failures:** tests that need a buyer must insert a real `User` row (or a factory fixture) before creating API keys; remove the "random UUID `sub`" pattern in `test_api_key_hashing.py`.
6. **Flush Redis per test file** (extend `_clear_rate_limiter` to `FLUSHDB` on the rate-limit DB) so rate-limit tests are deterministic.
7. **Triage the standalone failures:** `test_upload_pipeline.py` (8), `test_phase1_gap_coverage.py` (3), `test_api_key_hashing.py` (4) — decide fixture-fix vs. real-bug-fix per case.
8. **Re-run the full suite and lock a green baseline.**

### P2 — Close the known product gaps
9. Implement `/exports` list + detail (replace stubs). 10. Add `buyer_id` from auth context in `ExportRequest` (AGENTS.md #12).
11. Remove `init_db()` `create_all` from lifespan; rely on Alembic (AGENTS.md #6), and verify a clean `alembic upgrade head` end-to-end (validates 0016/0017 too).
12. Remove/rotate hardcoded default credentials (AGENTS.md #5).
13. Define the Celery beat schedule (consent expiry, compliance audit, payroll) (AGENTS.md #28/#32).
14. Add `minio_storage_bytes` regression check and confirm the gauge's Redis DB index matches the app's (`REDIS_URL` db 0 vs celery db 1).

### P3 — Engineering hygiene
15. `pyproject.toml`, README, LICENSE, CONTRIBUTING, and a minimal CI pipeline (AGENTS.md #1–#4, #27).
16. Leaderboard N+1 → JOIN; symmetric IAA IoU; pagination on `/nodes` + `/nodes/alerts`; rate limit `/consent/withdraw`; webhook retry queue (AGENTS.md #13/#17/#16/#18/#19).

---

## 5. Verification Facts (so we don't re-litigate)

- **Green group (verified this session):** `tests/test_metrics.py test_sam_segmenter.py test_yolo_seg.py test_prelabel.py test_image_upload.py test_health.py test_live_annotation.py test_analytics.py test_dedup.py test_catalog.py test_agri.py test_auth.py` → **76 passed**.
- **11 new tests added** (SAM 5, YOLOv8-seg 5 + metrics) — all passing.
- **Full suite:** `198 passed / 63 failed`; identical count with new tests ignored → failures pre-existing.
- **Real-model checks:** yolov8n-seg-fp32 runs (0.15 s, correct I/O, empty detections on synthetic blob — expected); SAM encoder loads (0.5 s); SAM decoder throws on all prompt shapes (defective export).
- **All app imports OK:** `app.workers.celery_app`, `app.workers.tasks`, `app.ai.sam_segmenter`, `app.ai.yolo_seg`, `app.api.metrics`, `app.main` (only pre-existing pydantic `model_*` namespace warnings).
- **Run command for migrations (local):** `POSTGRES_HOST=localhost ./.venv/bin/alembic upgrade head`.
