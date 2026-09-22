# EdgeVision-MW — Phase 9 Development Prompt
## Live Annotation Orientation Fix, Instance Masks & Object Tracking

**Date:** 12 August 2026
**Context:** EdgeVision-MW is a production-oriented AI annotation platform for Malawi road/agri imagery. The live-annotation surface (`/live-annotate` camera + screen capture, plus webcam capture on `/upload`) works end-to-end: browser sends JPEG frames over `/ws/annotate/live`, the backend decodes, runs a deployed detector, tracks objects, and streams boxes back over the WebSocket. Static annotation supports masks via YOLOv8-seg (`app/ai/yolo_seg.py`) and MobileSAM (`app/ai/sam_segmenter.py`).

**Current verified flow:** Start Camera (front-facing auto-mirrors the preview) → frames captured at 2 fps → POST/WS inference → boxes drawn in an SVG overlay on top of the video → Save Frame persists to MinIO + `annotations` table with `detected_objects`.

**Reported defect (verified root cause):** With a front-facing camera, the preview is CSS-mirrored and the annotation boxes, label text, and any text in the scene (signs, plates, OCR targets) render **flipped** — text is unreadable and boxes sit on the wrong side of objects. The saved frame and the boxes persisted to the DB are in raw coordinates while the screen shows mirrored coordinates, so the live view does not match what is captured or stored.

---

## Root Cause Analysis (verified)

| # | Location | Problem |
|---|----------|---------|
| 1 | `frontend/src/styles/studio-redesign.css:672-674` — `.live-annotate-video-wrapper.live-annotate-mirror { transform: scaleX(-1) }` | Mirrors the **entire wrapper** — the `<video>` **and** the `<AnnotationOverlay>` SVG. Both video and boxes/text are flipped together. |
| 2 | `frontend/src/pages/LiveAnnotatePage.tsx:69-77` | Auto-sets `mirrorPreview = facingMode !== "environment"` (any front camera → mirrored) with no user control. |
| 3 | `frontend/src/utils/captureFrame.ts:28` — `ctx.drawImage(video, 0, 0)` | Draws the **raw, un-mirrored** pixels. CSS transforms are never applied by `drawImage`, so the frame sent to inference and the frame saved to MinIO are un-mirrored. |
| 4 | `app/api/ws_annotation.py:75-105` | Backend is correct: decodes the received JPEG and returns boxes in **raw frame coordinates**. No flip anywhere on the server. |
| 5 | `frontend/src/styles/studio-redesign.css:1105` — `.camera-video.camera-mirror { transform: scaleX(-1) }` and `frontend/src/components/CameraCapture.tsx:105` | Upload-page webcam: preview is mirrored but `snap()` saves raw pixels. Preview ≠ saved file (broken WYSIWYG); any text the user frames appears backwards in the preview. |

**Why it looks the way it does:** the raw frame is analyzed (no mirror), boxes come back in raw coordinates, then the CSS flip mirrors the box overlay on screen — so on-screen boxes are mirrored relative to reality, and label text is rendered back-to-front. The two coordinate spaces (screen vs. frame) are inconsistent.

**Design invariant to enforce throughout this phase:** *The frame sent to inference and the frame saved to storage must always equal the frame the user sees, and annotation coordinates must always be expressed in the coordinate space of the analyzed frame.* Mirroring is a **data-level transform applied to the captured pixels before inference/save** — never a display-only CSS trick that desyncs from the data.

---

## Workstream A — Orientation Consistency (the fix)

### A1. Default to un-mirrored (raw) live preview
- In `LiveAnnotatePage.tsx`, replace the automatic `mirrorPreview` (line 69-77) with explicit user state `mirrored: boolean`, **default `false`**.
- When un-mirrored: no CSS transform on video or overlay. Camera frames, boxes, and text all render correctly and read left-to-right. Screen share must always be un-mirrored.
- Add a visible **"Mirror preview" toggle** in `live-annotate-controls` (i18n key `liveAnnotate.mirrorPreview`), persisted to localStorage so the user's choice survives navigation.
- Remove the `.live-annotate-video-wrapper.live-annotate-mirror` wrapper-level flip (studio-redesign.css:672). If a mirror is desired, apply `scaleX(-1)` to the **video element only** and mirror the captured pixels (A2) so boxes still align.

### A2. Make capture data-aware (`mirror` parameter)
- Extend `captureFrame(video, quality?, type?, mirror = false)` in `frontend/src/utils/captureFrame.ts`.
- When `mirror === true`, flip the pixels before encoding: `ctx.translate(w, 0); ctx.scale(-1, 1); ctx.drawImage(video, 0, 0);`.
- When `false` (default), unchanged.
- **Every caller must pass the same `mirrored` flag the preview uses:**
  - `useLiveAnnotation.ts` inference loop (line 124) — the frame analyzed must match the preview.
  - `useLiveAnnotation.ts` `saveFrame` (lines 153, 184) — the saved frame must match the preview **and** the analyzed frame.
- This single change guarantees the invariant: if the user enables mirroring, the analyzed/saved frame is truly mirrored, the overlay draws in mirrored coordinates, and everything aligns; if disabled (default), nothing is flipped anywhere.

### A3. Fix the upload-page webcam (`CameraCapture.tsx`)
- Default un-mirrored; keep/allow a "Mirror" toggle (facing button already exists).
- `snap()` (line 105) must apply the same pixel flip whenever the preview is mirrored, so the captured file is always WYSIWYG.
- Add an optional overlay hook (`onAnnotations?: LiveAnnotation[]`) so webcam snapshots can show the same live boxes as `/live-annotate` when both are active.

### A4. Persist orientation metadata
- In `save_live_annotation` (`app/api/annotations_live.py`), add `orientation: Literal["normal","mirrored"] = Form("normal")`.
- Store it in `ImageRecord.metadata_` and in the `detected_objects` payload (`{"objects": [...], "source": ..., "orientation": ...}`).
- Document that consumers (OCR via `app/ai/text_detection.py`, export builder, dedup) must un-mirror when `orientation === "mirrored"` (helper: `flipCoords`).

### A5. Shared coordinate helpers + tests
- Add `frontend/src/utils/orientation.ts` with pure functions: `flipBBoxX(bbox, width)`, `flipPolygonX(points, width)`, `mirrorFrame(ctx, w)`.
- Unit-test that flipping a bbox twice returns the original, and that `mirror=true` capture equals `mirror=false` capture flipped — under Vitest.

**Acceptance criteria (A):**
- Front camera live preview is un-mirrored by default; boxes sit exactly on the objects; box label text and any scene text read left-to-right.
- With "Mirror preview" ON, the video is mirrored, boxes stay aligned on the mirrored video, and the saved frame + persisted boxes are mirrored to match (consistent).
- Webcam upload saves exactly what the preview shows.
- Screen share is never mirrored.
- `orientation` is stored on every saved live frame.

---

## Workstream B — Instance Masks for Live Annotation

### B1. Emit masks over the WebSocket
- `app/api/ws_annotation.py`: when the active engine is segmentation-capable (deployed `road_segmentation` model, or `yolo_seg.py` `detect()` available), include per-detection masks.
- Payload per tracked object: `{ class_name, confidence, bbox, track_id, mask?: number[][] (polygon, normalized 0..1), mask_format: "polygon" | "rle" | null }`.
- Downsample/decimate mask polygons server-side so 2 fps stays interactive (cap points per polygon, e.g. ≤ 32).
- Respect the existing `ModelType` enum (`road_segmentation`, `agri_crop_classification`, `agri_health_classification`, `object_detection`).

### B2. Render masks in the overlay
- Extend `AnnotationOverlay.tsx` to draw mask polygons as translucent fills (`fillOpacity ~0.25`) with the same per-class color as the box.
- Add a "Boxes / Masks / Both" display toggle (i18n keys) defaulting to "Both".
- Masks must honor the same orientation invariant as boxes (A2/A5) — always drawn in the analyzed-frame coordinate space.

### B3. Persist masks on saved frames
- Extend `save_live_annotation` to accept optional `masks` (JSON array aligned with `annotations`).
- Store RLE or polygon in `detected_objects.objects[*].mask`. Reuse `mask_to_rle()` (`app/ai/sam_segmenter.py`) and verify the pycocotools path returns real RLE (it is now in `requirements.txt`); fall back to polygons when unavailable.

### B4. Static annotation mask priority (related fix)
- In the browser AI-assist path (`frontend/src/hooks/useAIAssist.ts`) and server prelabel path (`app/services/prelabel.py`), **prefer YOLOv8-seg masks over SAM** until `mobile_sam_decoder.onnx` is replaced with a working export (known defective). SAM stays secondary/optional.
- Render returned masks on `LabelCanvas` as editable polygons.

**Acceptance criteria (B):**
- Live road/agri streams show instance masks (people, vehicles, plants, road-surface regions) overlaid on the video in real time, correctly oriented.
- Masks persist with saved frames and appear in the exported manifest.
- Static annotation shows real YOLOv8-seg masks, not heuristic blobs.

---

## Workstream C — Robust Object Tracking

Current tracker (`app/ai/object_tracker.py`) is a greedy-IoU ByteTrack with no motion model, no class awareness, and 30-frame unlimited coasting — track IDs swap on busy scenes at 2 fps.

### C1. Motion model
- Add a per-track constant-velocity Kalman filter (x, y, w, h + vx, vy, vw, vh) with standard predict/update; predict before association each frame.
- Tune process/measurement noise for 2 fps webcams vs. 30 fps edge nodes.

### C2. Class-aware association
- Restrict matching to same-class detections (allow cross-class only as a label-carryover exception with a penalty).
- Replace greedy matching with optimal assignment (Hungarian) on the IoU cost matrix (scipy optional — include a small pure-Python fallback so the API container has no hard dependency).

### C3. Track lifecycle
- Per-class `max_age` (people/vehicles ~10-15 frames at 2 fps; slow-moving/stationary objects longer). Delete tracks past `max_age`.
- Confirmation threshold: tentative → confirmed after 3 consistent hits (keep), but reset `track_id` continuity cleanly on source/model change.
- On occlusion loss, keep the last bbox for `max_age` frames (coasting) instead of disappearing after one miss.

### C4. Optional ReID
- When a coasting track can't be matched by IoU, attempt re-association by CLIP embedding similarity of the predicted crop vs. candidate detections (reuse `app/ai/clip_embedder.py`). If not available, skip silently.
- Never let ReID change `class_name` of an existing track.

### C5. Per-domain tuning
- Expose a small config map (`app/ai/object_tracker.py` → `TrackConfig`) keyed by `ModelType`: e.g. road → prioritize vehicles/pedestrians, agri → prioritize plants, road_segmentation → segment-region labels. Provide `reset()` on model/source switch in `ws_annotation.py`.

**Acceptance criteria (C):**
- A car/pedestrian crossing the frame keeps one stable `track_id` (no swap) for ≥ 5 s at 2 fps in a scripted test with synthetic detections.
- Ids are stable across the same `model_type`/source; changing either resets cleanly.
- Tracker unit tests cover: association, ID continuity, class mismatch rejection, coasting, and reset.

---

## Workstream D — Domain Coverage & Text Readability

The user must be able to capture and annotate **people, vehicles, plants, and road surfaces** correctly — and any text must read properly.

### D1. Domain / model selector on Live Annotation
- Add a model-type selector to `LiveAnnotatePage` bound to `useLiveAnnotation({ modelType })` → WS `?model_type=` (currently hardcoded `"object_detection"` in `useLiveAnnotation.ts:39`).
- Options: `object_detection` (people/vehicles), `road_segmentation` (road surfaces/masks), `agri_crop_classification` (plants), `agri_health_classification`. Guard with backend availability (`No deployed model available` already handled in `ws_annotation.py:57`).
- Reset the tracker on selection change.

### D2. Taxonomy-aware labels
- Map COCO detections to the Malawi taxonomy client-side via `frontend/src/ai/taxonomyMapping.ts` and server-side via `SEG_TO_TAXONOMY` (`yolo_seg.py`). Overlay shows both, e.g. `car_private (car) 87%`, in both `en` and `ny`.

### D3. Text / OCR mode
- Add a `text_detection` mode using `app/ai/text_detection.py`: run OCR **only on un-mirrored frames** (`orientation === "normal"`); stream detected text regions as labeled boxes (`class_name` = recognized string, `confidence`).
- Block/disable OCR mode when the preview mirror toggle is ON (or automatically un-mirror the frame for OCR) — text must never be read backwards.
- Render recognized text boxes in `AnnotationOverlay` and persist with `detected_objects`.

**Acceptance criteria (D):**
- Selecting each domain streams the right detections/masks without a page reload.
- Road signage photographed with a front camera displays readable text in the overlay and in the saved frame.
- OCR results are never generated from mirrored frames.

---

## Technical Constraints

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), WebSocket on `/ws/annotate/live`, ONNX Runtime, Celery. Reuse `get_active_engine` (`app/ai/model_inference.py`) — do not hardcode model paths beyond the existing fallback chain.
- **Frontend:** React 18, TypeScript, Vite, Fabric.js, Dexie (offline sync must continue to use the same `mirror` flags), react-i18next. All new strings in `en.json` + `ny.json`.
- **Orientation invariant is mandatory:** analyzed frame = preview = saved frame, in both mirror modes (A2/A4).
- **No breaking changes:** existing `/live-annotate`, upload camera capture, static annotation, offline queue, and save endpoint contracts stay compatible (additive fields only).
- **Tests:** pytest for backend (WS mask/tracker, orientation metadata, OCR gating); Vitest for frontend orientation helpers and overlay rendering. Existing `test_live_annotation.py`, `test_live_annotation_ws.py`, `test_yolo_seg.py` must stay green.
- **Verify:** `npm run typecheck && npm run build` in `frontend/`; targeted pytest files green; manual smoke test with a front-facing camera.

---

## Suggested File Touch Points

### Backend
- `app/api/ws_annotation.py` — masks in WS payload, tracker reset, domain model_type passthrough
- `app/api/annotations_live.py` — `orientation` + `masks` form fields, persist metadata
- `app/ai/object_tracker.py` — Kalman motion model, class-aware Hungarian matching, per-class lifecycle, optional ReID
- `app/ai/yolo_seg.py` — polygon extraction/downsampling helpers for WS
- `app/ai/sam_segmenter.py` — verify `mask_to_rle()` against installed pycocotools
- `app/ai/text_detection.py` — expose OCR for the WS text mode (guard on orientation)
- `app/services/prelabel.py`, `app/services/clip_embed.py` — YOLOv8-seg mask preference
- `tests/test_live_annotation_ws.py`, `tests/test_object_tracker.py`, `tests/test_yolo_seg.py`, `tests/test_annotations_live.py`

### Frontend
- `src/pages/LiveAnnotatePage.tsx` — mirror toggle (default off), domain selector
- `src/utils/captureFrame.ts` — `mirror` parameter
- `src/utils/orientation.ts` — new coordinate helpers
- `src/hooks/useLiveAnnotation.ts` — pass mirror + modelType consistently (inference loop + saveFrame + offline queue)
- `src/hooks/useOfflineSync.ts` — persist `orientation` with queued live frames
- `src/components/AnnotationOverlay.tsx` — mask polygons, display toggle
- `src/components/CameraCapture.tsx` — WYSIWYG snap, optional overlay hook
- `src/components/LabelCanvas/*` — render masks as editable polygons
- `src/ai/taxonomyMapping.ts` — domain label mapping
- `src/styles/studio-redesign.css` — remove wrapper-level mirror, add video-only mirror + mask styles
- `src/i18n/locales/en.json`, `ny.json` — new keys

---

## Definition of Done for Phase 9

- [ ] Live camera preview is un-mirrored by default; boxes and label text are never flipped; scene text reads correctly
- [ ] "Mirror preview" toggle is data-consistent (analyzed = preview = saved) in both modes
- [ ] Upload webcam captures are WYSIWYG
- [ ] Live WS streams instance masks for people, vehicles, plants, and road-surface regions, correctly oriented
- [ ] Masks persist with saved frames and flow into the export manifest
- [ ] Tracker keeps stable IDs across ≥ 5 s at 2 fps in scripted and unit tests
- [ ] Domain selector (object_detection / road_segmentation / agri_*) works without reload; tracker resets on change
- [ ] OCR mode never runs on mirrored frames; recognized text renders readable
- [ ] `orientation` metadata persisted on all live frames; consumers documented
- [ ] All new backend tests pass; `test_live_annotation*.py`, `test_yolo_seg.py` green; frontend typecheck + build green; all new UI strings in `en` + `ny`

---

## Out of Scope (Future Phases)

- Re-exporting a working MobileSAM decoder ONNX (tracked separately as SAM repair)
- Browser-side on-device inference for live masks (server-side only this phase)
- Multi-camera / drone feed stitching
- Automated RL fine-tuning of track parameters
