# EdgeVision-MW — Phase 11 Development Prompt
## Depth-Accurate 3D, Export & Dedup Hardening, Live-Frame QA, Pipeline Performance & Offline Reliability

**Date:** 12 August 2026
**Context:** Phase 10 landed the four Phase 9 follow-ups plus 3D bounding boxes (monocular cuboids, yaw=0 MVP, gradient heuristic) — 31 backend tests + 10 Vitest green. Phase 11 closes the remaining honesty/perf/reliability gaps so live annotation results actually reach training datasets and exports, under real rural-network constraints (intermittent connectivity, low-bandwidth edge links, single 2D camera).

**Design invariant (carried over, mandatory):** *The frame sent to inference and the frame saved to storage must always equal the frame the user sees, and annotation coordinates (boxes, polygons, masks, 3D cuboid corners) must always be expressed in the coordinate space of the analyzed frame.* Orientation (`normal`|`mirrored`) is metadata that consumers un-mirror explicitly — never silently re-flipped.

---

## Verified Current State (code audit, 12 Aug 2026)

| # | Area | Verified fact |
|---|------|---------------|
| 1 | Depth | `app/ai/depth_estimator.py` has lazy singleton + `_heuristic_depth()` (vertical gradient, line 88-89); logs `depth_estimator_heuristic_only` (line 44) when model missing. Depth-Anything-V2-Small ONNX **not bundled** (deferred from Phase 10). |
| 2 | 3D | `app/ai/mono_3d.py`: `estimate_3d` / `attach_3d_boxes` (line 116), `_3D_CLASSES` gate, **yaw fixed 0**, class priors, intrinsics from `settings.CAMERA_FOV_DEG` (default 60°). |
| 3 | Export | `app/services/export_builder.py`: `SUPPORTED_FORMATS = ("COCO","YOLO","PASCAL_VOC")` (line 22); `_build_coco_json` (319), `_build_yolo_txt` (381), `_build_pascal_voc_xml` (422), `_preview_for_format` (87). No mask/RLE/`bbox_3d`/`orientation` handling in any builder yet. |
| 4 | Dedup | `app/services/dedup.py`: DCT pHash (64-bit, `_image_phash` line 76), Hamming (`_hamming` 99), `_phash_clusters` (133). **pHash is not mirror-invariant** → a frame saved mirrored vs normal hashes far apart and evades dedup. |
| 5 | QA/review | `app/api/review.py`: `review_queue` (31, filters `DatasetAssignment.status == "SUBMITTED"`), `review_job_detail` (70), `certify_job` (128), `reject_job` (176), `get_iaa_metrics` (225). Live frames land as `Annotation(status=PENDING)` with `dataset_id` — **no path routes them into QA/review**. |
| 6 | WS loop | `app/api/ws_annotation.py:96-128`: pull model — `receive_bytes()` → sync `cv2.imdecode` → inference → `send_json`. Client drives the 2 fps rate; no server frame-drop/backpressure, no warmup, no latency histogram. |
| 7 | Offline sync | `useOfflineSync.ts`: Dexie `liveFrameQueue` (v2 schema, has `bbox_3d`), `MAX_RETRIES=5`, `MAX_LIVE_FRAME_ENTRIES=50`, `MAX_LIVE_FRAME_BYTES=100MB`. No backoff/jitter, no checksum idempotency, no reconnect reconciliation, no eviction policy beyond hard caps. |
| 8 | Backend deps | `pycocotools` installed in `.venv`; `mask_to_rle` raises `ImportError` (no silent `""`). |

---

## Workstream A — Depth-Accurate 3D (close the Phase 10 deferral)

**Outcome:** real monocular depth drives cuboid distance/placement; rough yaw replaces the fixed `yaw=0`; the heuristic remains only as an offline fallback.

### A1. Bundle Depth-Anything-V2-Small ONNX
- Add the Depth-Anything-V2-Small ONNX artifact to `frontend/public/models/depth_anything_v2_vits.onnx` (follow the same deployment/loading pattern the other ONNX weights use) and document the download/verification step (sha256 in a `.sha256` sidecar or README note).
- `app/ai/depth_estimator.py`: wire the real ONNX path (lazy singleton, `get_depth_estimator()`, env `DEPTH_MODEL_PATH` override, input 518×518 resize, output = normalized inverse depth at input resolution, then resize to frame size). Keep `_heuristic_depth` as the `model_missing` fallback but label the payload `depth_available: false` so consumers know distance is heuristic-grade.
- Runtime budget: run at ≤ 256×256 internal resolution when possible; never add more than ~60ms to the WS budget (Workstream D owns the budget).

### A2. Depth-driven distance + rough yaw in `mono_3d.py`
- `estimate_3d(..., depth_map=None, ...)`:
  - Distance: median depth in a center window of the bbox when `depth_map` available (with a small center-offset bias toward the lower third — object feet region); else existing height heuristic.
  - **Yaw estimation (new, honest MVP):** when depth map available, estimate yaw sign+magnitude from the cross-bbox depth gradient (`(median_depth_left − median_depth_right) / bbox_width`), clamp to ±60°, convert to a rotation about the vertical axis; when no depth map, fall back to bbox-width-vs-prior ratio (`wider → more side-on`), clamped to ±60°; else `0`. Always emit `yaw_source: "depth_gradient" | "aspect_ratio" | "default"` and `distance_quality: "depth_map" | "heuristic"`.
  - Recompute the 8 corners with the estimated yaw; keep the projection math from Phase 10.
- `attach_3d_boxes` gains optional `depth_map` parameter; WS caller passes it when `depth_available` (A3).

### A3. WS + persistence exposure
- `app/api/ws_annotation.py`: run depth (when available) once per frame, pass to `attach_3d_boxes`; include `depth_available` at the result root and `bbox_3d.{yaw_source, distance_quality}` per object.
- `app/api/annotations_live.py`: accept and persist these new sub-fields as part of `bbox_3d` (JSONB — no schema change).
- Overlay label chip (Phase 10 E4) appends `≈` when `distance_quality === "heuristic"` (i18n both en+ny).

**Acceptance criteria (A):**
- Depth-Anything ONNX bundled + documented; `get_depth_estimator()` runs it end-to-end and returns a sane inverse-depth map on a synthetic test image.
- `estimate_3d` with a depth map whose left half is farther than the right returns a positive-yaw cuboid whose projected corners still fall inside the 2D bbox bounds.
- `tests/test_mono_3d.py` extended: yaw path (depth-gradient and aspect-ratio), `yaw_source`/`distance_quality`/`depth_available` fields, fallback equivalence when depth is `None`.
- Overlay renders `≈12.3 m` for heuristic distances; text differs for depth-grade distances.

---

## Workstream B — Export & Dedup Hardening

**Outcome:** exported artifacts carry masks (polygon+RLE), `bbox_3d`, and orientation; dedup catches mirrored vs normal duplicates.

### B1. Export builders emit full payloads
- `app/services/export_builder.py`:
  - **COCO** (`_build_coco_json`): per annotation add `segmentation` (list of polygons from `mask` when `mask_format === "polygon"`), `area` (from RLE area or polygon), `bbox` (already), and `attributes: {class_name, confidence, track_id, orientation, mask_format, mask_rle?, bbox_3d?}`. Add `info.orientation_mode` so consumers know frames may need un-mirroring (`flipCoords` documented).
  - **YOLO / YOLO-Seg** (`_build_yolo_txt`): standard lines unchanged; when masks exist, emit a companion **YOLO-Seg** `.txt` (same filename, `-seg` suffix) with `class cx cy w h` + normalized polygon points, and note it in the manifest/`_preview_for_format`.
  - **PASCAL_VOC** (`_build_pascal_voc_xml`): include `<segmentation>` polygon per object when present; add `<metadata>` block with orientation + `bbox_3d` attributes.
  - `_preview_for_format` shows mask overlay + an "orientation: mirrored" badge + `≈` distance chips, so reviewers see exactly what ships.
- No layout/format breaking changes to existing parsers: all additions are additive fields.

### B2. Mirror-aware dedup
- `app/services/dedup.py`: make dedup orientation-invariant without losing orientation fidelity:
  - For each candidate image compute both `phash(image)` and `phash(mirror(image))` (cheap flip before DCT). Cluster by min-Hamming across both, i.e. A and mirror(A) land in the same cluster with `members: [{annotation_id, image_path, orientation, phash}]`.
  - Persist cluster `orientation_mixed: true` when a cluster contains both normal and mirrored members — surface in the dedup UI/API response so operators can pick which copy to keep (recommend normal when available, since mirrored frames are a display convenience).
  - Keep existing Hamming threshold behavior; extend `_phash_clusters` and the dedup endpoint response only.
- Add a `tests/test_dedup.py` case: mirror(A) hashes within threshold of A's mirrored-hash and clusters together; a genuinely different image does not.

**Acceptance criteria (B):**
- Export preview + COCO/YOLO/YOLO-Seg/VOC outputs verified on a live-captured frame with mask + `bbox_3d` + mirrored orientation; a downstream consumer (the test) re-parses the artifact and recovers polygon + attributes.
- Dedup: mirrored copy of the same scene clusters with the original; `orientation_mixed` flag set; no false cluster for a different scene.
- `pytest tests/test_export_builder.py tests/test_dedup.py` (new files) green.

---

## Workstream C — Live-Frame QA/Review Workflow

**Outcome:** live-captured frames ride the existing review lifecycle — assign → QA review → certify/reject — with an audit trail, so certified frames feed dataset builds.

### C1. Route live frames into review
- `app/api/review.py`: extend `review_queue` to include `Annotation.status == PENDING` rows with `metadata_['live_capture'] == true` and a `dataset_id` (parameter `scope: "live" | "jobs" | "all"`, default `all`). Reuse the assignment mechanism (`app/services/annotation.py` auto-assign) so live frames become assignable to ANNOTATOR/QA.
- Add batch actions for live frames only: `POST /review/live/approve` and `POST /review/live/reject` accepting `annotation_ids[]` + optional reason — bulk-transition `PENDING → CERTIFIED` (approve) or `REJECTED` (reject), each writing an `AuditLog` entry (`event_type="live_frame_review"`, actor, ids, reason).
- Certified live frames must be eligible for dataset build stratified sampling (verify `build_dataset_task` / catalog path already includes CERTIFIED `Annotation` rows for `dataset_id` — if it filters by status, add CERTIFIED).

### C2. TurboReview support for live frames
- `TurboReview.tsx`: add a "Live captures" filter; when reviewing a live frame, reuse Phase 10 assets — render mask polygons (Workstream B B4 overlay style) and `bbox_3d` cuboids with the same overlay mode toggle; allow mask/cuboid **refine** (move vertices) via the same controls LabelCanvas exposes, saved as `human_labels` edits on the Annotation.
- Show orientation badge + `depth_available`/`distance_quality` chips so the QA can judge 3D estimates honestly.
- i18n: new strings in both `en.json` and `ny.json`.

### C3. IAA guard (do not overreach)
- Live-frame QA is single-reviewer approval; **do not** run two-annotator IAA for live frames in this phase (document in code). Keep existing IAA path for `/jobs` untouched.

**Acceptance criteria (C):**
- A live-captured frame with `dataset_id` appears in `review_queue?scope=live`; approve → CERTIFIED + audit log; reject → REJECTED + reason; both idempotent on double-submit (409/422 on already-final status).
- A certified live frame is included in a subsequent dataset build for that `dataset_id`.
- TurboReview renders masks + cuboids + orientation/distance chips for a live frame; refine saves to `human_labels`.
- `pytest tests/test_review_live.py` (new) green.

---

## Workstream D — Live Pipeline Performance

**Outcome:** the 2 fps live loop stays within a documented latency budget under load, with drop/backpressure policies and metrics instead of unbounded queuing.

### D1. Server-side budget + frame policy
- `app/api/ws_annotation.py`: measure end-to-end per-frame latency (already computes `inference_ms`); add a per-connection rolling budget:
  - If processing exceeds `WS_FRAME_BUDGET_MS` (default 500) → set a `dropping` flag, reply with a lightweight `{"status":"busy","drop":true}` instead of a full result for the next frame, then resume.
  - Guard decode: skip empty frames (already), and reject frames while a heavy engine call is in flight (no concurrent inference per connection) — pipeline is naturally serialized today; make the guard explicit.
- Warmup: after `websocket.accept()`, fire a background `asyncio.create_task` to warm the active engine (and depth estimator if enabled) so the first real frame is not the slowest; log `ws_warmup_ms`.

### D2. Metrics
- `app/api/metrics.py`: add Prometheus counters/histograms: `ws_annotate_frames_total`, `ws_annotate_dropped_frames_total`, `ws_annotate_latency_ms` (histogram), `ws_annotate_connect_duration` — instrument the WS loop; add a `depth_inference_ms` histogram.

### D3. Client-side adaptive rate + drop-oldest
- `useLiveAnnotation.ts`: measure WS round-trip latency; if rolling average > 800ms, decay capture rate 2fps → 1fps (floor); restore when healthy. Never enqueue more than one in-flight frame — send **only the latest** captured frame (drop intermediate) to avoid pile-up (matches server serialization).
- Only skip inference frames; **save** and **mirror** behavior must remain unaffected (the drop policy applies to the analysis loop only, preserving the WYSIWYG invariant).

**Acceptance criteria (D):**
- With a synthetic slow engine stub, the server emits `{"status":"busy","drop":true}` under overload and `ws_annotate_dropped_frames_total` increments; no unbounded queue growth server-side.
- Client reduces rate under simulated latency and never has >1 in-flight analysis frame.
- Metrics present at `/metrics`; `tests/test_ws_metrics.py` (new) or an extension of `test_live_annotation_ws.py` asserts counters fire.

---

## Workstream E — Offline Sync Reliability

**Outcome:** queued live frames survive flaky rural connectivity — retried with backoff, de-duplicated by checksum, reconciled on reconnect, evicted safely.

### E1. Backoff + jitter for both queues
- `useOfflineSync.ts`: replace fixed retries with exponential backoff: delay = `min(2^retryCount * 1000 + jitter(±250), 30000)`; honor server `retry-after` if present in the failed response; cap `retryCount` at 6 then surface in the sync UI as "needs attention".
- Apply to both `syncQueue` and `liveFrameQueue` replays; keep `MAX_RETRIES` semantics but derive from the schedule.

### E2. Checksum idempotency + reconnect reconciliation
- Add `checksum?: string` (sha-256 of the frame blob) to `LiveFrameQueueEntry`, computed at enqueue.
- Before replay after reconnect: `GET` the dataset's recent `checksum_sha256` set (existing `ImageRecord`/`Annotation` data) and skip any queued frame whose checksum already exists server-side → mark `resolved` with `lastError: "duplicate_checksum"`. Prevents the mirrored/normal double-save and retry storms on partially-applied frames.
- `save_live_annotation` already checks nothing idempotently; note in code comment that the client owns dedup via checksum (server stays stateless on this path).

### E3. Safe eviction policy
- Replace hard-cap truncation with a policy: when `MAX_LIVE_FRAME_ENTRIES` (50) or `MAX_LIVE_FRAME_BYTES` (100MB) exceeded, evict oldest **`resolved`/`failed` (beyond retry cap)** entries first; never drop `pending`. Log evictions to console + a `sync_stats` event.
- Expose counts (pending/syncing/failed/resolved) in the existing sync UI.

### E4. On-device fallback polish (tie-in with Workstream D3)
- When `VITE_ENABLE_LIVE_ONDEVICE_SEG` is on and the WS is down: capture at adaptive rate (D3), run `detectAllSeg` (Phase 10 D), queue via `liveFrameQueue` with `annotations`, `engine: "ondevice"`, `checksum`; on reconnect, reconcile via E2 then replay. Payload already carries orientation/masks/`bbox_3d` (verify `bbox_3d` from on-device is absent — on-device seg has no depth; that is expected and documented).

**Acceptance criteria (E):**
- Under a mocked flaky server (fail n times then succeed), a queued live frame syncs with observed backoff delays and ends `resolved`; retry storm avoided.
- Re-queueing a frame whose checksum already exists server-side resolves as `duplicate_checksum` without a POST.
- Eviction drops only resolved/failed beyond cap; pending frames never lost; counts accurate.
- `vitest` new `useOfflineSync` tests (pure helpers extracted for testability) green.

---

## Technical Constraints (all workstreams)

- **Backend pattern parity:** new lazy singletons/warmup follow `get_sam_segmenter()` / `get_depth_estimator()` conventions (process-wide lock, env-configurable path, graceful `None`).
- **No schema migrations:** everything is JSONB/additive (`detected_objects`, `metadata_`, queue entries).
- **i18n:** every new string lands in **both** `en.json` and `ny.json`.
- **No new heavy deps:** Depth-Anything is a model artifact (bundled/URL, not a pip/npm package); no new runtime libraries.
- **Honesty invariants:** 3D remains an estimate (yaw_source/distance_quality/depth_available always emitted); live QA is single-reviewer (no fake IAA); on-device seg carries no depth.
- **Tests:** follow existing conventions — pytest (async, `db_session`/`test_client` fixtures) and Vitest (pure functions extracted for testability).

## File Touch-Points

| Workstream | Backend | Frontend | Tests |
|-----------|---------|----------|-------|
| A | `app/ai/depth_estimator.py`, `app/ai/mono_3d.py`, `ws_annotation.py`, `annotations_live.py`, `app/core/config.py` (depth env) | `AnnotationOverlay.tsx` (chip), `types/index.ts`, `public/models/depth_anything_v2_vits.onnx`, i18n | `test_mono_3d.py`, new `test_depth_estimator.py` |
| B | `app/services/export_builder.py`, `app/services/dedup.py` (+ dedup endpoint response) | export/dedup UI badges | new `test_export_builder.py`, `test_dedup.py` |
| C | `app/api/review.py`, `app/services/annotation.py` (assign), catalog build eligibility | `TurboReview.tsx`, i18n | new `test_review_live.py` |
| D | `app/api/ws_annotation.py`, `app/api/metrics.py`, `app/core/config.py` (budget env) | `useLiveAnnotation.ts` | extend `test_live_annotation_ws.py`, `test_ws_metrics.py` |
| E | (server stateless; optional checksum GET endpoint) | `useOfflineSync.ts` (+ pure helpers), sync UI | `vitest` `useOfflineSync` |

## Definition of Done

- All five workstream acceptance criteria pass; full pytest suite (existing 31 + new) and Vitest suite green; `npm run typecheck` + `npm run build` green.
- Manual verify on live-annotate: depth-grade distance + yaw chips when model present, heuristic `≈` otherwise; export preview shows masks/cuboids/orientation; a mirrored capture dedups with its normal twin; live frame can be assigned → reviewed → certified → included in a dataset build; overloaded loop emits `drop:true` and client slows to 1fps; airplane-mode save → reconcile → no duplicate frame after reconnect.
- No silent RLE, no silent depth fallback (always labeled), no CSS mirror on the overlay (Phase 10 guard intact).

## Out of Scope

- Two-annotator IAA for live frames; stereoscopic/LiDAR 3D; per-frame bundle adjustment.
- Server-side frame persistence retry (client owns checksum idempotency; server remains stateless on `/annotations/live`).
- Full worker-queue profiling/autoscaling of Celery tasks.
- New annotation-format standards beyond the existing COCO/YOLO/VOC families.
