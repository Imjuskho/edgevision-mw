# Road Segmentation — Fix to 100% (Agent Prompt)

You are working in the **EdgeVision-MW** repo at `/Users/mac/EDGE VISION DATA PLATFORMS/edgevision-mw`.
Stack: Python 3.12 + FastAPI + SQLAlchemy async + Celery backend; React 18 + Vite + Fabric.js frontend;
PostgreSQL 16 + Redis + MinIO via Docker Compose. Full architecture in `AGENTS.md`.

## Mission

The **Road Segmentation annotation feature** is supposed to let an annotator load a frame, run
"Auto Segment", see the detected road-surface regions (good_road / pothole / crack / dust_road /
gravel_road / road_marking / shoulder) as editable polygons on the canvas, accept/reject them, and
save the annotations. It currently works at roughly **2%**: auto-segment returns JSON, but almost
nothing useful ever renders on the canvas and the labels are semantically garbage. Your job is to
diagnose every link in the chain and make the feature genuinely work end to end. Treat the definition
of done below as non-negotiable.

## How to work

1. Read every file listed in "Map of the feature" below (and follow imports).
2. Reproduce each suspected bug before fixing it. The whole stack is running already:
   - Backend: `http://localhost:8000` (docs at `/docs`), frontend: `http://localhost:3000`
   - DB/worker helpers: `docker compose exec app ...`, `docker compose exec postgres psql -U edgevision -d edgevision_mw`
3. Fix root causes, not symptoms. Do not paper over errors with `try/except` that swallows them —
   many of the current failures are exactly that.
4. Run the verifications at the bottom and iterate until green.

## Map of the feature (read all of these)

Backend:
- `app/ai/road_segmenter.py` — ONNX/YOLO inference, `_preprocess`, `_postprocess`, NMS, polygon/RLE extraction, `resolve_road_seg_model_path`, `get_road_segmenter`, `classify_surface_type`
- `app/api/road.py` — `/road/segment`, `/road/segment/batch`, `/road/result/{id}` GET/PATCH, `/road/classes`, `/road/analyze`
- `app/schemas/road.py` — `InstanceMask`, `RoadSegmentationRequest/Response`, etc.
- `app/workers/tasks.py` (`auto_label_road_task`, ~line 1351) — batch road segmentation path
- `app/ai/model_inference.py` — deployed-model resolution + `_download_artifact` (this is what actually loads the deployed demo model)
- `app/models/enums.py` — `ModelType.road_segmentation`
- `scripts/seed_minio.py`, `scripts/download_ai_models.sh`, `scripts/train_road_seg.py`, `scripts/export_road_seg_onnx.py` — model provisioning

Frontend:
- `frontend/src/pages/SegmentPage.tsx` — the road segmentation page (`workspaceMode="segment"`), `handleAutoSegment`, `renderSegmentResults`, `handleSave`
- `frontend/src/hooks/useRoadSegmentation.ts` — `segmentViaApi`, `loadModel`, accept/reject state
- `frontend/src/components/RoadSegPanel/RoadSegPanel.tsx` — side panel, stats, accept/reject/save buttons
- `frontend/src/components/RoadSegPanel/FabricPolygonManager.ts` — polygon draw/edit on Fabric canvas
- `frontend/src/constants/roadTaxonomy.ts` — `ROAD_SURFACE_CLASSES` (7 classes, ids 0–6)
- `frontend/src/services/api.ts` — `segmentRoad`, `segmentRoadBatch`, `updateRoadResult`, `getRoadResult`, `getRoadClasses`
- `frontend/src/ai/onnxManager.ts` — on-device ONNX runtime (the local path)

Tests & reference:
- `tests/test_road_segmenter.py`
- `PHASE8_ROAD_SEGMENTATION_PROMPT.md` and `PHASE15_ANNOTATION_UNIFICATION_PROMPT.md` (design intent + the coordinate-normalization invariant)

## Root causes already confirmed (fix these; do not skip)

### A. The deployed model is NOT a road model (most important)
The active deployed model row is:
`road_segmentation | minio:9000/edgevision-data-lake/models/demo/road_segmentation/best.onnx | active`
That file is **YOLOv8n-seg trained on COCO (80 classes)**. Verified from the ONNX metadata:
`custom_metadata_map.description = "Ultralytics YOLOv8n-seg model trained on coco.yaml"`, names =
person/bicycle/car/... It detects vehicles and pedestrians, not roads. Evidence in the DB:
`road_annotations.instances` contains `crack`, `road_marking`, `class_7`, `class_36` — these are
COCO class ids (`car=2 → crack`, `truck=7 → class_7`, `skateboard=36 → class_36`) blindly mapped
through `ROAD_CLASS_NAMES[cid]` in `road_segmenter.py:281`.
**Fix:** the `/road/segment` endpoint must not silently use an arbitrary deployed/fallback model.
It must use a road-trained segmentation model. Look at `scripts/train_road_seg.py` +
`scripts/export_road_seg_onnx.py` (intended pipeline) and `frontend/public/models/yolov8n-seg-fp32.onnx`
(which is byte-identical in size to the demo model and is also COCO — verify, then replace or stop
using it). If no trained road ONNX exists in the repo, that is a blocker: make model resolution
explicit and *fail loudly* with the current 503 message instead of silently degrading to a garbage
model, and document exactly which model file the feature is allowed to use.

### B. `cv2` NameError kills every mask (proof that polygons are always empty)
`road_segmenter.py` imports `cv2` only inside `_preprocess` (line 166). `_postprocess` calls
`cv2.resize` at line 244 with no import in scope → `NameError` → swallowed by the bare
`except Exception:` at line 278 → `mask = zeros(...)`, `mask_rle=""`, `polygon=None`.
Verified in the DB: every `road_annotations.instances.polygon` is empty. The frontend then skips
every instance (`renderSegmentResults`: `if (!inst.polygon || inst.polygon.length <= 2) continue`)
→ nothing is ever drawn. **Fix:** import `cv2` at module top; and never swallow this silently — log
the actual exception with `logger.error(..., exc_info=True)`.

### C. Letterbox transform is never undone
`_preprocess` (lines 160–177) letterboxes the frame to 640×640 with scale + padding (`dx, dy`), but
`_postprocess` normalizes boxes with `/640` (lines 224–227) and resizes masks straight to
`(orig_w, orig_h)` (line 244) without cropping the padding first. On any non-square frame the
geometry is shifted/compressed vs the real image. **Fix:** store `scale, dx, dy` from preprocess on
the segmenter (or return them), crop the mask to the letterboxed content region, then scale.
Apply the same transform to the bbox before normalizing. This must keep the Phase-15 invariant:
coordinates are normalized to the *analyzed frame* and round-trip exactly between canvas and JSON.

### D. YOLO `.pt` path never produces geometry
`_segment_yolo` (lines 120–150) sets `mask_rle=""` and never builds `polygon`. If the model
resolver ever lands on a `.pt`, the page is silent-dead again. **Fix:** extract masks from the
Ultralytics `result.masks` (with the same letterbox correction) or explicitly reject `.pt` weights
for this endpoint.

### E. Frontend "local model" path is dead code
`useRoadSegmentation.segmentImage` (line 95) calls `segmentViaApi` in *both* branches — the
`onnxManager` on-device path never runs (and `SegmentPage` doesn't even call `segmentImage`).
**Fix:** either wire the on-device path for real or delete it and make the API path the single
source of truth. The page must always call the same backend endpoint the tests cover.

### F. Save flow must persist what the annotator sees
`SegmentPage.handleSave` collects only Fabric objects flagged `_isRoadPolygon`, then separately
PATCHes accepted hook `annotations`. Verify end-to-end that: drawn+accepted polygons round-trip to
`PATCH /road/result/{id}` with non-empty normalized `polygon` and correct `class_id`, `reviewed`
becomes true, and reloading the page (`GET /road/result/{id}`) re-renders them at the same spot.
Also verify `auto_label_road_task` produces the same polygon-bearing instances for the batch endpoint.

### G. Taxonomy/version coherence
`ROAD_SURFACE_CLASSES` ids 0–6 must equal the model's class index order for the *road* model.
Enforce `ROAD_TAXONOMY_VERSION` consistency between `/road/classes` and the saved instances.
`classify_surface_type` (lines 392–406) is only meaningful once the class ids are real road classes.

## Definition of done (what "100%" means — all must pass)

1. **Real model in use:** `/road/segment` uses a road-trained segmentation model (never COCO).
   Its class names map 1:1 to `ROAD_SURFACE_CLASSES` by id, and `/road/classes` agrees.
2. **Masks render:** for a road frame, auto-segment returns ≥1 instance whose `polygon` has >2
   points and `mask_rle` is non-empty; `renderSegmentResults` draws every such polygon on the
   canvas at the correct position and scale (verify against a non-square test frame).
3. **Editable + reviewable:** drawn polygons can be edited via `FabricPolygonManager`; accept /
   reject per instance and accept-all/reject-all update the panel and the canvas correctly.
4. **Save round-trip:** `handleSave` → `PATCH /road/result/{id}` persists instances with accurate
   normalized polygons/classes; `GET /road/result/{id}` returns them; reloading the page draws them
   identically. `reviewed=true`, `auto_generated=false` after a human save.
5. **Batch:** `/road/segment/batch` → `auto_label_road_task` produces the same quality instances
   (with polygons) for every image and lands them in `road_annotations`.
6. **No silent degradation:** every failure mode (missing model, inference error, empty result)
   is either a correct HTTP status (503/500) or an explicit user-visible message — never a silently
   empty polygon list caused by a swallowed exception.
7. **Quality signal:** the panel's "Good Road %" and stats are derived from *real* road instances,
   not from mislabeled COCO detections. Confirm on a known road frame that
   `good_road/pothole/crack` classes actually match what's visible.
8. **Tests:** `tests/test_road_segmenter.py` extended to cover: correct letterbox undo (mask +
   bbox), polygon extraction non-empty, class mapping, and that `/road/segment` returns 503 (not a
   garbage result) when only a COCO model is available. Frontend gates pass (`npm run typecheck`,
   `npm run test`, `npm run build`, contrast check) and backend suite passes.

## Verification commands

```bash
# Backend (run inside repo root; the Docker app container runs uvicorn)
docker compose exec app pytest tests/test_road_segmenter.py -v
docker compose exec app pytest tests/ -q          # must stay green (331 passed / 1 failed / 6 errors baseline; the pre-existing failures are known, don't regress anything)

# Inspect deployed model (should NOT say "trained on coco.yaml" for road_segmentation)
docker compose exec app python -c "import onnxruntime as ort; s=ort.InferenceSession('/tmp/edgevision-model-cache/models/demo/road_segmentation/best.onnx', providers=['CPUExecutionProvider']); print(s.get_modelmeta().custom_metadata_map)"

# Inspect stored road results
docker compose exec postgres psql -U edgevision -d edgevision_mw -c "SELECT annotation_id, surface_type, jsonb_array_length(instances::jsonb) AS n FROM road_annotations ORDER BY updated_at DESC LIMIT 10"
docker compose exec postgres psql -U edgevision -d edgevision_mw -c "SELECT (i->>'class_name') AS cls, (i->>'polygon') AS poly FROM road_annotations, jsonb_array_elements(instances::jsonb) i LIMIT 10"

# Manual E2E: open http://localhost:3000 → the road segmentation page → Auto Segment on a frame
# → expect polygons drawn, then Save → reload → same polygons.

# Frontend gates
cd frontend && npm run typecheck && npm run test && npm run build
```

## Reporting back
When done, summarize: (1) each root cause and the fix, with `file:line`; (2) which model is now
used and how it's resolved; (3) the round-trip test you ran (image → API → canvas → save → reload);
(4) test/gate results. If a true road-trained ONNX model does not exist in the repo and must be
trained/exported first, say so explicitly and give the exact commands/scripts to produce it.
