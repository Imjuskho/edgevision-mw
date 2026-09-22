# Cursor Prompt — P0 Sprint: CI Green + MobileSAM Fix + Label-Correction Workflow

You are working in **EdgeVision-MW** at `/Users/mac/EDGE VISION DATA PLATFORMS/edgevision-mw`.
Stack: Python 3.12 + FastAPI + SQLAlchemy async + Celery; React 18 + Vite + Fabric.js; PostgreSQL 16 + Redis + MinIO via Docker Compose. Read `AGENTS.md` first.

This sprint covers the three P0s from the system study:
**P0-1 CI green** (8 failing tests + Ruff → 0), **P0-2 MobileSAM decoder fix/replacement**, **P0-3 label-correction workflow** (tooling so humans can correct 30–50 frames, then export them for a retrain). Do all three; the work order below is intentional.

A prior prompt (`CURSOR_ROAD_SEG_FIX.md` in the repo root) covers the road-seg model/geometry pipeline — do not regress what it set up. Reuse its conventions.

---

## P0-1 — CI green

### A. Fix the 8 failing tests

**A1. `tests/test_studio_ai.py` — 3 failures (`assert 500 == 200` at lines 54, 135, 157).**
Root cause (verified): `pydantic_core.ValidationError: AIAnnotation.confidence — Input should be less than or equal to 1, input_value=36.896...`. The `/studio/label/ai-assist` endpoint (`app/api/studio_ai.py`, `ai_assist` at line 73) builds `AIAnnotation` objects whose `confidence` must be in [0,1] (schema line 56), but the YOLO fallback detector returns an out-of-range value (36.9).
Fix:
- Find where confidence is produced in `app/ai/yolo_detector.py` (see `confidence=conf` at lines 73, 100, 109) and apply a sigmoid or clamp so it is always in [0,1] at the source.
- Add a defensive clamp in `app/api/studio_ai.py` before constructing every `AIAnnotation` (e.g. `confidence=min(1.0, max(0.0, conf))`), so no validation error can surface again.
- All 4 tests in `tests/test_studio_ai.py` must pass (the 3 above + `test_ai_assist_rejects_missing_image`). Do not break the fallback contract: when models are unavailable, the endpoint still returns 200 with `fallback=true`.

**A2. `tests/test_object_tracker.py` — 5 failures (`AttributeError: module 'numpy' has no attribute 'long'`).**
Root cause (verified): dependency mismatch in the host `.venv`. `pip check` reports: `scipy 1.18.0` requires `numpy>=2.0,<2.8`, `opencv-python 5.0.0.93` requires `numpy>=2`, `tifffile 2026.7.31` requires `numpy>=2.1`, but the venv has **numpy 1.26.4**. scipy's `_sputils.py` uses `np.long` (removed in numpy 1.24) → crashes inside ByteTrack's Hungarian match (`app/ai/object_tracker.py:175` → `scipy.optimize.linear_sum_assignment`).
Fix:
- Upgrade numpy in `.venv` to a version satisfying every package (e.g. `numpy>=2.1,<2.8`), then run `.venv/bin/python -m pip check` and confirm it is clean.
- Pin it in `requirements.txt` (replace line 22 `numpy>=1.26.0` with a compatible pin, e.g. `numpy>=2.1,<2.8`) so CI/host installs match.
- Grep `app/` for numpy aliases removed in 2.x (`np.float`, `np.int`, `np.long`, `np.bool`, `np.unicode`, `np.object`, `np.complex`) and fix any usage with the modern equivalent (`np.float64`, `np.int64`, `bool`, `object`).
- `tests/test_object_tracker.py` must go 9/9 green (5 currently failing + 4 passing).

### B. Ruff → 0

Current (measured fresh, `app/` + `tests/`): **164 errors**. Categories to expect: ARG005×16, UP042×15, F841×14, ARG002×12, E702×11, RUF046×11, F401×8, RUF001×6, SIM105×6, B007×5, RUF002×4, RUF006×4, B905×3, I001×3, SIM102×3, SIM117×3, SIM108×2, and one-offs (B017, B023, E402, E712, E741, F823, RUF022, SIM115, SIM118, UP028, UP046).

Approach:
1. `.venv/bin/ruff check app/ tests/ --fix`, then `--unsafe-fixes`, then handle the rest manually.
2. Keep runtime behavior identical: E702 (split statements), F841 (delete unused vars), ARG005/ARG002 (prefix unused args `_` or remove), E712 (`== True` → `is True`), RUF001/002 (replace ambiguous unicode with ASCII), SIM105/115 (use `with` / `suppress`), RUF006 (store `asyncio.create_task` handles), B007 (loop vars → `_`), UP042/UP046/RUF046 follow ruff's suggested rewrite.
3. While in there, fix the previously-flagged **real runtime bugs**, not just lint: `cv2` NameError in `app/ai/road_segmenter.py:244` and `app/ai/agri_segmenter.py:249` (masks silently degrade to zeros), `settings` undefined in `app/services/training.py` (18 uses), `HTTPException` undefined in `app/api/billing.py:86`.
4. Finish at `ruff check app/ tests/` → **0 errors, 0 warnings**. Run the full test suite after (`331 passed / 1 failed / 6 errors` is the known baseline; the 1 failed + 6 errors are documented pre-existing — do not regress anything beyond fixing the 8 above).

---

## P0-2 — MobileSAM decoder fix/replacement

File: `app/ai/sam_segmenter.py`. `_load` (lines 108–134) probes the decoder; on any failure it sets `_decoder_session=None`, so `_loaded=False` and `predict_point`/`predict_box` silently fall back to empty square masks (`_heuristic_point`/`_heuristic_box`, lines 283–296). Line 127 comments: *"the bundled export fails at runtime on all prompt shapes."*

Models on disk: `frontend/public/models/mobile_sam_encoder.onnx` (~28 MB), `frontend/public/models/mobile_sam_decoder.onnx` (~20 MB). The `_decode` contract it feeds is: `image_embeddings [1,256,64,64]`, `point_coords`, `point_labels`, `mask_input [1,1,256,256]`, `has_mask_input`, `orig_im_size`, expecting `[1,N,256,256]` (or `[N,256,256]`) masks.

Steps:
1. **Reproduce first:** instantiate `SAMSegmenter()`, capture the exact probe exception from `_load` (input name / rank / shape mismatch, or a hard op error). Log it verbatim.
2. **Replace the decoder ONNX** with a known-good export, in priority order:
   - The official `mobile_sam_decoder.onnx` from the MobileSAM project (ChaoningZhang/MobileSAM) release assets, SHA256-verified and pinned (record the URL + checksum in a comment or `docs/`).
   - Or re-export locally: `pip install git+https://github.com/ChaoningZhang/MobileSAM` and run its `export_decoder.py` (ONNX opset consistent with the existing encoder).
3. If input names/ranks differ from the current `_decode`, update the token/rank mapping (lines 114–125, 195–205) rather than forcing the old convention.
4. Validate:
   - The `_load` probe passes → `is_loaded()` is True.
   - `predict_point` on a real 4K traffic frame from `datasets/road_seg_traffic/images/` returns a **non-trivial mask** (report foreground pixel count and coverage %), and clearly beats the heuristic fallback (mask IoU vs heuristic > 0.3).
   - `predict_box` likewise.
5. Tests: extend `tests/test_sam_segmenter.py` — assert `is_loaded()` True when both ONNX files exist and `predict_point` returns a non-empty mask; keep the graceful-degradation path for when models are absent (skip, don't fail).
6. If no network is available to obtain a replacement and local re-export fails, **do not fake a fix** — document the exact blocker (what export/URL is needed) and leave the graceful fallback in place.

---

## P0-3 — Label-correction workflow (unblock retrain)

Context: humans will correct frames in Studio at `http://localhost:3000/datasets/lilongwe-traffic-road-seg/segment` (dataset id `23952171-1159-4eff-844d-8f30fb3c98db`, name "Lilongwe Traffic Road Seg"). `app/models/road_annotation.py` stores `instances` JSONB as a list of `{class_id, class_name, confidence, bbox, mask_rle, polygon}` on `annotation_id` (FK → `annotations.id`). `SegmentPage.handleSave` PATCHes accepted instances via `PATCH /road/result/{annotation_id}` (`app/api/road.py:375`), which sets `reviewed=true`, `auto_generated=false`. Frame filenames in the dataset look like `IMG_3045_f0001_t2.0s.jpg` (178 frames in `datasets/road_seg_traffic/`, 152 train / 26 val, currently with only heuristic labels — that's why the model is weak).

Deliverables:

1. **`scripts/export_road_labels.py`** — export human-corrected Studio annotations to YOLO-seg labels for retraining:
   - Query `road_annotations` joined to `annotations` where `reviewed=true` (prefer rows where `auto_generated=false`).
   - Resolve each `annotation.image_path` (MinIO object key); basename is the frame filename. Download the frame from MinIO (helpers exist in `app/ai/model_inference.py::_download_artifact` / `app/core/dependencies.py`; reuse the MinIO client pattern from `app/api/road.py`).
   - Write one `.txt` per frame, YOLO-seg format: `class_id x1 y1 x2 y2 ...` (normalized 0–1) taken from `instances[].polygon` (skip instances with empty/too-short polygons). Map `class_id` per `road_dataset.yaml`.
   - Write into a **new** split dir, `datasets/road_seg_corrected/{images,labels}/{train,val}/` (copy the matching frames from `road_seg_traffic`) so you never clobber the auto-generated set; produce `road_dataset_corrected.yaml` (7 classes, same names/order).
   - Print a per-class histogram and a list of frames that had no corrected annotations (so the human can see coverage gaps).
2. **`scripts/render_road_overlays.py`** — draw polygons over the corrected frames → `runs/label_gen/overlay_*.jpg` (one per corrected frame, plus the 5 from the auto-gen set for comparison). This is the "review 5 overlays" quick win; a human uses these to spot-check label quality.
3. **Retrain recipe** (documented in the script docstrings and this sprint's report): once ≥30 frames are corrected → `python scripts/train_road_seg.py --data road_dataset_corrected.yaml --epochs 30 --batch 4 --device mps|cpu --imgsz 640 --name road_v2 --project runs/segment`, then export the best `.pt` to `models/road_seg/best.onnx` (via `scripts/export_road_seg_onnx.py`), replacing the demo model. Bump the hardcoded `model_version="yolov8n-seg-v1"` in `app/api/road.py` (lines 124, 131, 151) to track the new model.
4. **Quick win from the report** — raise the road confidence threshold default from 0.35 to **0.5–0.6**:
   - Add a `ROAD_SEG_CONF_THRESHOLD` setting in `app/core/config.py` (default `0.5`), read it in `app/api/road.py` (`segment_image`, currently `request.conf_threshold`) and/or `app/ai/road_segmenter.py`, and set it in `.env`.
   - Keep frontend in sync: `frontend/src/services/api.ts::segmentRoad` default `confThreshold = 0.35` → `0.5`.
   - Do not break the existing response schema.

---

## Verification

```bash
# Deps sanity
.venv/bin/python -m pip check                              # must be clean after numpy upgrade
# Tests
.venv/bin/python -m pytest tests/test_studio_ai.py tests/test_object_tracker.py -q   # 13/13 green
.venv/bin/python -m pytest tests/test_sam_segmenter.py -q  # SAM probe + predict tests green
.venv/bin/python -m pytest tests/ -q                       # no regressions vs baseline
# Ruff
.venv/bin/ruff check app/ tests/                           # 0 errors
# Label export (after ≥1 corrected road_annotation exists)
.venv/bin/python scripts/export_road_labels.py --dataset-id 23952171-1159-4eff-844d-8f30fb3c98db --reviewed-only
.venv/bin/python scripts/render_road_overlays.py
# Live API (backend runs on :8000)
curl -s http://localhost:8000/health | head -c 200
# Studio page for human correction
open http://localhost:3000/datasets/lilongwe-traffic-road-seg/segment
```

---

## Report back
1. **CI:** exact numpy/scipy resolution chosen, `pip check` output, ruff before/after counts, full test-suite delta.
2. **Studio AI:** where confidence was unclamped and the fix (`file:line`).
3. **MobileSAM:** the reproduced probe error, what replaced the decoder (URL/checksum or re-export), probe + predict-point results (fg pixels / coverage %), IoU vs heuristic.
4. **Labels:** how many corrected `road_annotations` existed, export histogram, overlay path, and the exact retrain command ready to run.
5. Any blocker you could not clear (with the exact fix needed).
