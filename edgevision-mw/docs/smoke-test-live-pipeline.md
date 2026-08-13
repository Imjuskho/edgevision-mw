# Live Pipeline Smoke Test Runbook

Manual verification for the EdgeVision live annotation → QA → export path. **Instructions only** — run each stage when your stack is up unless noted.

**Design invariant:** The frame sent to inference/saved is the frame the user sees. QA refinements persist normalized 0..1 coordinates in analyzed-frame space.

---

## Stage 1 — Pre-flight

**Prerequisites:** Docker (or local Postgres/Redis/MinIO), Python venv, Node 20+, repo cloned.

**Steps:**

1. Start infrastructure: `docker compose up -d postgres redis minio` (or equivalent).
2. Apply migrations: `alembic upgrade head`.
3. Download depth model: `./scripts/download_depth_model.sh`.
4. Verify checksum: `shasum -a 256 -c frontend/public/models/depth_anything_v2_vits.onnx.sha256`.
5. Start API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
6. Health: `curl -s http://localhost:8000/health | jq .status` → `"ok"`.
7. Metrics: `curl -s http://localhost:8000/metrics | head` → Prometheus text (includes `edgevision_*`).
8. Depth smoke (Python): `get_depth_estimator().estimate_depth_map(synthetic_image)` → `depth_available: true`, no `depth_estimator_heuristic_only` log.

**Expected:** All checks green; ONNX artifact present (~94 MB, SHA256 `afb6a5c28f3b6bf1618c6e43f02073ef9dfdc70e937502d51603e57b0a1df10c`).

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| Health not ok | Postgres/Redis/MinIO down or wrong env vars |
| Checksum fail | Partial download — re-run download script |
| heuristic_only log | Model missing or wrong path (`frontend/public/models/depth_anything_v2_vits.onnx`) |
| Alembic error | DB unreachable or stale migration state |

---

## Stage 2 — Live annotate

**Prerequisites:** Stage 1 pass; frontend `npm run dev`; user with `liveAnnotate` feature; camera or test pattern.

**Steps:**

1. Open **Live Annotate** (`/live-annotate`).
2. Enable camera; toggle **Mirror preview** on/off — overlay boxes stay aligned with video (WYSIWYG).
3. Open browser devtools → confirm debug probe shows analyzed frame dimensions matching capture.
4. Switch source to **Screen share**; capture one frame with at least one detection.
5. Save frame; note annotation ID in network tab.

**Expected:** Saved frame matches preview; coords in analyzed-frame space; live save returns 201 with `orientation` and `depth_available` fields.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| Overlay drift when mirroring | CSS transform on overlay (invariant violation) |
| Empty save | WebSocket/API auth failure or empty annotations JSON |
| Screen share blocked | Browser permission denied |

---

## Stage 3 — Masks + 3D

**Prerequisites:** Live capture with segmentation enabled; depth model loaded (Stage 1).

**Steps:**

1. In Live Annotate, set display mode to **Masks** or **All**.
2. Confirm polygon overlays render on detections.
3. Switch to **3D** view; confirm cuboid wireframe on objects.
4. Check UI chips: **Depth: onnx** when model loaded; **Depth: heuristic** when model absent.
5. With mirror on, confirm chip **Orientation: mirrored** and coords still align.

**Expected:** Masks and cuboids visible; depth chip reflects ONNX vs heuristic backend state.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| No masks | YOLO-Seg model not loaded or confidence below threshold |
| heuristic chip always | Depth ONNX missing or inference error |
| Cuboid misaligned | Display mode vs coord space mismatch |

---

## Stage 4 — Save & review

**Prerequisites:** Pending live capture from Stage 2; QA/ADMIN token.

**Steps:**

1. `GET /api/v1/review/live/queue` — confirm capture listed.
2. Open **Review** / TurboReview session for dataset.
3. `GET /api/v1/studio/sessions/{id}/review-queue?limit=10` — verify `detected_objects`, `has_human_labels`, `annotations`.
4. Approve one image via TurboReview (↑) and submit batch.
5. Confirm response: `"processed": 1`.
6. DB/API: annotation `status` = `CERTIFIED`, `is_certified` = true.
7. Reject a second capture; confirm `REJECTED`.
8. Flag a third; confirm status stays `PENDING`.

**Expected:** Submit maps `approve→approved`, `reject→rejected`, `flag→flagged`; `AnnotationAction` records `review_approved` / `review_rejected` / `review_flagged`.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| processed: 0 | Submit sent legacy `action` without mapping (fixed in 11B) or wrong `image_id` |
| Flag certifies | Backend not keeping PENDING on flagged |
| Queue empty | Wrong scope or capture not linked to session dataset |

---

## Stage 5 — Refine

**Prerequisites:** Review queue item with `detected_objects[].mask` or `bbox_3d`.

**Steps:**

1. In TurboReview, enable **Refine masks & 3D**.
2. Drag a mask vertex (cyan handle, ≤32 points) — dirty indicator appears.
3. Drag a cuboid corner (orange handle, 8 corners).
4. Submit with approve; inspect `qa_labels.refines` via `GET /api/v1/studio/annotations/{id}`.
5. Confirm `human_labels` unchanged.

**Expected:** Refines stored under `qa_labels.refines` only; `AnnotationAction` type `refine`; coords in 0..1 analyzed-frame space; UI note explains 2D projection correction.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| 422 on submit | >32 mask points, ≠8 cuboid corners, or coords outside 0..1 |
| human_labels mutated | Review submit touching annotator labels |
| Refines missing | Submit payload missing `refines` array |

---

## Stage 6 — Export

**Prerequisites:** At least one CERTIFIED annotation with masks.

**Steps:**

1. Open **Export** for dataset.
2. Run export as **COCO** (includes RLE masks when available).
3. Run **YOLO-Seg** and **VOC** formats.
4. Download artifact; spot-check one annotation includes refined mask/bbox if QA applied.

**Expected:** Export jobs complete; formats contain segmentation polygons/RLE consistent with `qa_labels.refines` merge rules in export builder.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| Empty export | No certified rows or filter too strict |
| Missing masks | pycocotools not installed or mask_format unsupported |
| Stale geometry | Export reading `detected_objects` only — verify export_builder QA merge |

---

## Stage 7 — Dedup

**Prerequisites:** Dataset with mixed-orientation or near-duplicate live captures.

**Steps:**

1. Open **Dedup** panel for dataset.
2. Run scan; look for groups tagged `orientation_mixed`.
3. Resolve one group (keep best quality frame).
4. Confirm removed duplicate no longer appears in review queue.

**Expected:** Dedup detects orientation mismatch strategy; resolution persists.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| No groups | Threshold too high or insufficient embeddings |
| orientation_mixed missing | Orientation metadata not stored on capture |
| Resolve fails | Permission or FK constraint on annotation delete |

---

## Stage 8 — Offline

**Prerequisites:** PWA/service worker registered; prior live session with saved frames.

**Steps:**

1. DevTools → Application → Service Worker active.
2. Capture frames while online; note checksums.
3. Stop backend WebSocket / go offline (DevTools Network → Offline).
4. Confirm on-device queue retains pending saves.
5. Restore network; verify sync reconciles via `GET /api/v1/annotations/live/checksums`.
6. Confirm no duplicate rows for same checksum.

**Expected:** Offline queue drains on reconnect; checksum reconcile prevents duplicates.

**Fail → likely cause:**

| Symptom | Cause |
|---------|--------|
| SW not registered | Build without Vite PWA plugin or HTTP (not HTTPS/localhost) |
| Lost saves | IndexedDB cleared or private browsing |
| Duplicate rows | Checksum reconcile not called post-sync |

---

## Quick commands

```bash
# Backend tests (review + depth)
pytest tests/test_studio_review.py tests/test_depth_estimator.py -q

# Frontend
cd frontend && npm run typecheck && npm run test -- --run && npm run build

# Depth artifact
./scripts/download_depth_model.sh
shasum -a 256 -c frontend/public/models/depth_anything_v2_vits.onnx.sha256
```
