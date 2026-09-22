# Cursor Prompt — Train Road Segmentation Model + Fix Pipeline to 100%

You are working in the **EdgeVision-MW** repo at `/Users/mac/EDGE VISION DATA PLATFORMS/edgevision-mw`.
Stack: Python 3.12 + FastAPI + SQLAlchemy async + Celery; React 18 + Vite + Fabric.js; PostgreSQL 16 + Redis + MinIO via Docker Compose. Architecture reference: `AGENTS.md`. Read it first.

## Mission

The Road Segmentation feature is at ~2%: it must reach 100%. The user has decided the path:
1. **Train a real road model** with `scripts/train_road_seg.py` from the frames in `datasets/road_seg_traffic/` (the dataset has 178 frames, 152 train / 26 val, but **zero labels** — you must auto-generate YOLO-seg polygon labels with the on-disk MobileSAM ONNX models + road-color/texture heuristics).
2. Export the trained weights to `models/road_seg/best.onnx`.
3. Set `ROAD_SEG_MODEL_PATH` to `models/road_seg/best.onnx`.
4. **Reject COCO-pretrained models** so the pipeline never silently uses a generic model again.
5. Fix the confirmed backend bugs that currently make polygons always-empty, then verify E2E.

Do all steps. Do not stop after training — the deployment wiring and backend fixes are part of "100%".

---

## Step 0 — Confirmed state & evidence (reproduce before fixing)

- Deployed active model row: `road_segmentation | minio:9000/edgevision-data-lake/models/demo/road_segmentation/best.onnx`. Its ONNX metadata says `description = "Ultralytics YOLOv8n-seg model trained on coco.yaml"`, 80 COCO names (person/bicycle/car/...). It is NOT a road model.
- `frontend/public/models/yolov8n-seg-fp32.onnx` is byte-identical in size (13,873,434 bytes) to that COCO model — verify (metadata + sha256) and stop using it for road seg.
- `app/ai/road_segmenter.py` has a **`cv2` NameError at line 244** (`cv2.resize` in `_postprocess`; `cv2` is only imported inside `_preprocess` line 166). The resulting exception is swallowed by the bare `except Exception:` at line 278, so every instance is returned with `polygon=None`, `mask_rle=""`. Verified: every `road_annotations.instances.polygon` in Postgres is empty/NULL.
- `_preprocess` (lines 160–177) letterboxes to 640×640 (scale + `dx,dy` padding) but `_postprocess` normalizes boxes with `/640` (lines 224–227) and resizes masks straight to `(orig_w, orig_h)` (line 244) **without cropping the padding** → geometry is shifted/compressed on non-square frames.
- `_segment_yolo` (lines 120–150) never emits masks/polygons (`mask_rle=""`, no polygon) — a `.pt` path is also dead.
- Stored DB instances contain `crack`, `class_7`, `class_36`, `road_marking` — COCO ids (`car=2`, `truck=7`, `skateboard=36`) blindly mapped via `ROAD_CLASS_NAMES[cid]` at line 281.
- Frontend `useRoadSegmentation.ts` `segmentImage` (line 95) calls `segmentViaApi` in **both** branches — the on-device `onnxManager` path is dead code. `SegmentPage.tsx` uses `segmentViaApi` directly. Single source of truth = the backend `/road/segment` endpoint.
- `app/api/road.py`: `POST /road/segment` (line 66), `POST /road/segment/batch` (line 156 → `auto_label_road_task`), `GET/PATCH /road/result/{id}` (lines 347, 375), `GET /road/classes` (line 415).
- `app/ai/model_inference.py`: `get_road_segmenter`-adjacent deployed-model machinery (`_download_artifact`, `get_active_deployed_model`, `_get_local_fallback_engine`). The local fallback list for `ModelType.road_segmentation` includes `yolov8n-seg.pt` (COCO). This is the path that must reject COCO.

## Step 1 — Environment

- Host `.venv` has **no torch/ultralytics** (`requirements-training.txt` exists with `ultralytics>=8.3.0`, `torch>=2.0.0`). Install into `.venv`:
  `uv pip install --python .venv/bin/python -r requirements-training.txt` (or `pip install` if uv absent). torch can be large — if the Mac has a MPS-capable M-series chip, use the default PyPI wheel (Apple silicon wheels support MPS); do NOT use CUDA wheels on macOS.
- Confirm GPU/accelerator: `python -c "import torch; print(torch.__version__, torch.backends.mps.is_available())"`; pass `--device mps` (or `cpu`) to training accordingly.
- Check `wheelhouse/` for pre-staged wheels before any download; prefer offline install if complete.

## Step 2 — Auto-generate labels (MobileSAM + heuristics)

Create `scripts/generate_road_labels.py`. It must produce YOLO-seg format labels (one `.txt` per frame in `datasets/road_seg_traffic/labels/train/` and `labels/val/`, same basename as the image, normalized 0–1 polygon coordinates: `class_id x1 y1 x2 y2 ...`), classes exactly matching `road_dataset.yaml` (0 good_road, 1 pothole, 2 crack, 3 dust_road, 4 gravel_road, 5 road_marking, 6 shoulder).

Approach:
1. **SAM region proposals:** Use the on-disk MobileSAM ONNX models `frontend/public/models/mobile_sam_encoder.onnx` + `frontend/public/models/mobile_sam_decoder.onnx` to get object-agnostic instance masks. Check `app/ai/mobile_sam.py` for the existing wrapper — REUSE it if its probe passes (AGENTS.md warns "MobileSAM decoder ONNX export is defective"; probe first, run a decoder sanity check on one frame).
   - Encoder at 1024×1024; auto-prompt with a grid of foreground points (e.g., a 12×12 grid over the lower 2/3 of the frame, and/or low-color-variance seed points inside the road region). Merge masks to instances.
2. **Road-class heuristic assignment** per mask, using color/texture statistics inside the mask:
   - **road_marking (5):** high luminance / low saturation (white) or yellow-orange stripes — `V>200, S<60` in HSV, or strong yellow hue.
   - **pothole (1):** dark, low-luminance, high local variance against surrounding road (`V<80`), roughly round/compact shape.
   - **crack (2):** thin, elongated dark regions — high aspect ratio skeleton / small area relative to its elongated bbox, dark.
   - **dust_road (3):** light brown / tan dirt — hue 15–40, `S 30–70, V 60–90` (calibrate on a few frames).
   - **gravel_road (4):** brownish-gray with high texture energy (std-dev / Laplacian variance above dust_road).
   - **good_road (0):** smooth dark asphalt/gray — low texture, `V 60–120`, low saturation; fill for road-region pixels not otherwise classified.
   - **shoulder (6):** road-adjacent bands at frame left/right edges with non-road color/texture, or beyond the detected drivable surface.
   - Resolve conflicts by confidence ordering (e.g., pothole > crack > marking > gravel > dust > good) and reject masks below a minimum pixel area (relative to frame).
3. **Clean up:** keep only masks within the road area (center-weighted region, roughly the lower ~2/3 of the frame, accounting for horizon); apply morphological closing to smooth boundaries; drop masks overlapping a larger mask by >70%; simplify polygons (remove redundant points, cap max points ~ 40 per mask) and emit valid YOLO-seg polygons. Log a per-class histogram.
4. If the SAM decoder probe fails outright, **fall back to pure heuristics** (color/texture segmentation with connected components + the same classifier) so labels are still generated — but print a clear warning. The user explicitly approved "SAM + heuristics"; never block on SAM.
5. Verify output: every frame has a label file (or a documented reason); label classes are only 0–6; coordinates in [0,1]; `train`/`val` splits match the image dirs. Spot-check by rendering 3–5 overlaid frames to `runs/` and viewing them.

## Step 3 — Train + export

- Train: `python scripts/train_road_seg.py --data road_dataset.yaml --model yolov8n-seg.pt --epochs 100 --imgsz 640 --batch 8 --device mps|cpu --name road_v1 --project runs/segment`
  - You need `yolov8n-seg.pt` (COCO-pretrained base is fine as the *training starting point*; what we reject is deploying a COCO model). Download it if missing (Ultralytics assets), or reuse any seg checkpoint on disk.
  - If 100 epochs is too slow on CPU, reduce to the largest feasible count (min 30) with `patience` early-stop; report final mAP and the best epoch.
- Export to the exact path the app will load: copy the trained `runs/segment/road_v1/weights/best.pt` → `models/road_seg/best.pt`, then export ONNX with `scripts/export_road_seg_onnx.py --weights models/road_seg/best.pt --output models/road_seg/` and rename the produced file to **`models/road_seg/best.onnx`**.
- Verify the ONNX metadata: run the road_segmenter ONNX path against one frame and confirm non-empty polygons + class names in 0–6 range.

## Step 4 — Configuration

- Set `ROAD_SEG_MODEL_PATH=models/road_seg/best.onnx` in `app/core/config.py` default AND in `.env` (keep them consistent). In `app/core/config.py` this field is at line 62 (`ROAD_SEG_MODEL_PATH: str = ""`).

## Step 5 — Reject COCO-pretrained models (backend)

In `app/ai/road_segmenter.py` and `app/ai/model_inference.py`:
1. Add a metadata check when an ONNX model is loaded for road segmentation: parse `custom_metadata_map["names"]` (or `description`); if it does not match the road taxonomy (must contain `good_road`/`pothole`/`crack`/`dust_road`/`gravel_road`/`road_marking`/`shoulder`, or at least be non-COCO — reject if `person`/`car`/`bicycle` appear), **refuse to load** it and log clearly.
2. In `model_inference.py::_get_local_fallback_engine`, remove COCO candidates (`yolov8n-seg.pt`, `yolov8x.pt`) from the `road_segmentation` fallback list; if only COCO is available, do NOT fall back — the `/road/segment` endpoint must return its existing 503 ("Road segmentation model not available... set ROAD_SEG_MODEL_PATH") instead of silently degrading. Keep the 503 behavior for `get_road_segmenter` when nothing valid is found.
3. In `get_road_segmenter` (`road_segmenter.py:365`), the deployed-model branch must validate the downloaded artifact the same way before constructing the segmenter.
4. Add tests in `tests/test_road_segmenter.py`: (a) loading a COCO-ONNX → rejected / `is_loaded()` False; (b) a stub road-ONNX → accepted; (c) `/road/segment` returns 503 (not garbage) when only COCO is available.

## Step 6 — Fix the geometry pipeline (`app/ai/road_segmenter.py`)

1. Import `cv2` at module top (kill the line-244 NameError). Remove the bare `except Exception:` at line 278 — replace with `except Exception as exc: logger.error(..., exc_info=True)` so mask failures are never silent.
2. **Undo letterbox correctly:** in `_preprocess` return/store `scale, dx, dy`; in `_postprocess` crop the mask to the letterboxed content region `[dy:dy+nh, dx:dx+nw]` before resizing to `(orig_h, orig_w)`, and normalize boxes with the same inverse transform (not `/640`). Keep the Phase-15 invariant: normalized coords must map exactly onto the analyzed frame.
3. Fix `_segment_yolo` to extract real masks from `result.masks` (apply the same letterbox undo) and emit `mask_rle` + `polygon`; or explicitly fail with a clear message if `.pt` can't produce masks. Do not return box-only instances.
4. Keep `classify_surface_type` (lines 392–406) semantics intact — it only becomes meaningful once class ids are real road classes.

## Step 7 — Verify E2E ("100%")

1. Restart/let Docker pick up `.env` changes (the app container is `edgevision-mw-app-1`, entrypoint runs alembic then uvicorn; `.env` is consumed via env vars — confirm the container sees the new path, e.g. `docker compose exec app python -c "from app.core.config import settings; print(settings.ROAD_SEG_MODEL_PATH)"`).
2. `docker compose exec app pytest tests/test_road_segmenter.py -v` and the full `tests/` suite (baseline: 331 passed / 1 failed / 6 errors — those pre-existing failures are known; don't regress anything).
3. Manual E2E against a real frame: call `POST /api/v1/road/segment` with an image_id from an existing `annotations` row whose `image_path` exists in MinIO. Assert response has ≥1 instance with non-empty `polygon` (>2 points) and `mask_rle`, correct class ids 0–6. Then `PATCH /road/result/{id}` with accepted instances, `GET /road/result/{id}`, confirm round-trip.
4. Frontend: `cd frontend && npm run typecheck && npm run test && npm run build` all green. Open the road segmentation page at `http://localhost:3000`, load a frame, Auto Segment → polygons drawn; Save → reload → same polygons.
5. Confirm the panel's "Good Road %" and stats are derived from real road instances.

## Deliverables / report back
Summarize: (1) label-generation results (per-class histogram, SAM probe pass/fail, fallback used); (2) training run (epochs, device, final mAP50/mAP50-95, best epoch, training time); (3) final model path + ONNX metadata names; (4) every code fix with `file:line`; (5) E2E test results; (6) if anything in Steps 2–3 couldn't be completed, say exactly what blocked it and what you did instead.

Verification commands to keep handy:

```bash
# config visible to app container
docker compose exec app python -c "from app.core.config import settings; print(settings.ROAD_SEG_MODEL_PATH)"
# model metadata (must be road names, NOT coco)
docker compose exec app python -c "import onnxruntime as ort; s=ort.InferenceSession('/tmp/edgevision-model-cache/models/demo/road_segmentation/best.onnx', providers=['CPUExecutionProvider']); print(s.get_modelmeta().custom_metadata_map.get('names'))"
# stored results
docker compose exec postgres psql -U edgevision -d edgevision_mw -c "SELECT annotation_id, surface_type, jsonb_array_length(instances::jsonb) AS n FROM road_annotations ORDER BY updated_at DESC LIMIT 10"
# backend tests
docker compose exec app pytest tests/test_road_segmenter.py -v
# frontend gates
cd frontend && npm run typecheck && npm run test && npm run build
```
