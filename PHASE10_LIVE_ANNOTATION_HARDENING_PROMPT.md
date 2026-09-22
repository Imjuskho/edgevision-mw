# EdgeVision-MW — Phase 10 Development Prompt
## Live Annotation Hardening: Studio Mask Wiring, RLE Persistence, Orientation Verification, On-Device Segmentation & 3D Bounding Boxes

**Date:** 12 August 2026
**Context:** Phase 9 delivered orientation consistency (mirror toggle default off + localStorage, `captureFrame(mirror)` pixel flip, `orientation.ts` + Vitest, WYSIWYG webcam snap, `mask_to_polygon()`/`attach_mask_polygons()` in `yolo_seg.py`, Kalman+Hungarian class-aware tracker, mask polygons streamed over `/ws/annotate/live`, 28 backend tests passing). This phase closes the four verified gaps Phase 9 left behind and adds 3D bounding boxes for the object classes where a monocular 3D estimate is meaningful.

**Design invariant (carried over, mandatory):** *The frame sent to inference and the frame saved to storage must always equal the frame the user sees, and annotation coordinates (boxes, polygons, masks, 3D cuboid corners) must always be expressed in the coordinate space of the analyzed frame.* Mirroring is a data-level pixel transform applied before inference/save — never a display-only CSS flip that desyncs from the data.

---

## Verified Current State (code audit, 12 Aug 2026)

| # | Area | Verified fact | Implication |
|---|------|---------------|-------------|
| 1 | `app/api/annotations_live.py:241` | `_attach_mask_rle(ann_list, width, height)` **is** already invoked on every live save; `_polygon_to_mask()` (line 24) rasterizes normalized polygons. | Workstream C is *not* "wire the call" — it is **install the dependency + harden + test**. |
| 2 | `requirements.txt:27` vs venv | `pycocotools>=2.0.7` is declared **but NOT installed** in `.venv` (`python -c "import pycocotools"` → ModuleNotFoundError). | `mask_to_rle()` (`sam_segmenter.py:313-322`) silently returns `""` → **RLE is a runtime no-op today**. Must be fixed or documented honestly. |
| 3 | `LabelCanvas.tsx:167-181` | `handleFullImageAI` already creates Fabric `Polygon` objects from `det.polygon`. | Wiring is partial — polygons exist but labels/classes and save round-trip are wrong (see B). |
| 4 | `LabelCanvas.tsx` `handleSave` | Polygon save path hardcodes `class: "car"` and normalizes points by `imgW * scaleX` in a way that is inconsistent between polygon and rect paths. | Polygons saved from Studio carry wrong classes / misaligned coordinates. |
| 5 | Overlay mirror | Design is correct: when mirrored, capture flips pixels → detections come back in mirrored coords → video element is CSS-flipped → overlay drawn **un-flipped** in mirrored coords aligns exactly. Double-flipping the overlay would misalign it. | Workstream A is *verification/reconciliation*, not a "add the CSS mirror to overlay" change. |
| 6 | `onnxManager.ts` `MODEL_REGISTRY` | `yolov8n_seg` entry exists (input `1,3,640,640`, output `1,116,8400` + `1,32,160,160`); `initModels` warms it. | Backend logic port (NMS + proto-mask decode) is the only missing piece for on-device seg. |
| 7 | 3D boxes | `grep` for `3d_bbox|depth_estimation|cuboid` across the repo → **no matches**. | Entirely greenfield. |

---

## Workstream A — Orientation Verification & Reconciliation (follow-up A: "overlay mirror check")

**Outcome:** prove (not assume) that overlay alignment holds in both orientations, and fix any real discrepancy found.

### A1. Debug orientation self-check
- In `LiveAnnotatePage.tsx`, behind a dev-only flag (env `VITE_ENABLE_ORIENTATION_DEBUG`), add a small on-screen "orientation probe": a fixed marker drawn at a known screen point (e.g. 25% / 75% from left) on the **captured** frame and the **overlay**, both rendered simultaneously.
- When the probe is active, compare the on-screen marker positions of the two layers. They must coincide pixel-for-pixel in both `mirrored=false` and `mirrored=true`. Any offset → log a structured warning (`console.warn`, key `orientation_mismatch`) with the measured delta and the current `mirrored` state.

### A2. Guarantee single source of truth for the mirror flag
- Audit and enforce that exactly one expression computes "is the display mirrored" and that the **same** value feeds: (1) the video CSS class, (2) `captureFrame(…, mirror)`, (3) the `mirroredRef`/state. Extract it to one function `isMirrored()` (or reuse `orientationFromMirror`) and use it in `LiveAnnotatePage.tsx:44` and `:190` and `CameraCapture.tsx`.
- The `<AnnotationOverlay>` must **never** apply `scaleX(-1)` or any CSS transform, in any display mode (boxes, masks, 3D, both, all). Add a code-level guard: a `useEffect` that throws/asserts the overlay root has no transform class.
- When mirroring is active, `AnnotationOverlay` receives `previewMirrored={true}` **only** so it can flip debug coordinates / depth probes identically to the data — never to flip the rendered annotation layer.

### A3. Automated math verification (Vitest)
- Extend `orientation.test.ts` with identity tests: `flipBBoxX(flipBBoxX(b,w),w) === b`; same for `flipPolygonX` and the new `flipCuboidX` (A4 uses it).
- Test that a capture with `mirror=true` equals a `mirror=false` capture flipped — already present; keep green.
- New: a "coordinate round-trip over WS" test using a mock WebSocket that mirrors what the server does: given a flipped image, detections are returned in flipped coords, and the overlay draw function (pure, extracted to `utils/drawAnnotations.ts`) produces SVG coordinates identical to `flipBBoxX(rawCoords, w)`.

### A4. Extend orientation helpers for new payloads
- Add to `orientation.ts`: `flipCuboidX(corners, width)` (flips `bbox_3d.corners2d`), `flipMaskPolygonX(points, width)` (already exists as `flipPolygonX` — alias it for mask polygons).

**Acceptance criteria (A):**
- With the debug probe on, marker coincidence holds at 0px delta for both orientations on a real front camera and on screen share.
- No code path can apply a CSS flip to `AnnotationOverlay`; a lint/test assertion enforces it.
- New identity/round-trip Vitest tests pass.

---

## Workstream B — LabelCanvas Mask Wiring (follow-up B4)

**Outcome:** AI-detected instance masks (from prelabel API / SAM / YOLOv8-seg) render on the Studio canvas as **editable, correctly-classed Fabric polygons**, and save back the same shape with the right class.

### B1. Carry class + confidence onto polygons
- `useAIAssist.ts` `aiDetectAll()` already maps `det.polygon` into `box.polygon` for results that carry one. Ensure every mask-returning engine path (prelabel API `detect()`, SAM refine, offline browser seg from Workstream D) attaches `polygon` **and** `className`/`confidence`.
- In `LabelCanvas.tsx` `handleFullImageAI`, create each Fabric `Polygon` with:
  - `points` in absolute canvas coordinates (already done), and
  - custom properties `name` / `(label: className)` and `confidence`, so both `canvas.getActiveObject()` and `handleSave` can read them.
- Give each polygon the class color from the existing taxonomy color map (same map used for rects) with `fill` at `rgba(…, 0.15)` and a solid stroke so filled polygons do not hide the underlying pixels.

### B2. Polygons must be editable
- Keep Fabric's default `Polygon` controls (vertex dragging) and `selectable=true`. A double-click on a polygon body re-runs nothing by default; instead open the existing class-assignment UI (the same dropdown used for rect re-classification) pre-filled with the polygon's class so the user can re-label.
- Rect⇄polygon coexistence: a rect and its polygon from the same detection are one logical annotation. Implement a lightweight link: `handleSave` writes the rect's class/label and the polygon together under the same `annotationId` so Studio review/export sees one object.

### B3. Correct save round-trip
- Fix the polygon branch of `handleSave`:
  - Read `points` from the Fabric object's current (possibly transformed) state via `polygon.points.map(p => ({x: p.x, y: p.y}))`, apply the same `scaleX`/`scaleY` compensation used by the rect path, then **normalize once** consistently (`x / (imgW * scaleX)`, `y / (imgH * scaleY)`) — the current `imgW * scaleX` denominator for both axes is wrong when aspect ratio differs.
  - Persist `class` from `polygon.label ?? polygon.name` (no hardcoded `"car"`), plus `confidence` and `source: "ai_polygon" | "manual_polygon"`.
  - Emit `mask_format: "polygon"` and keep the normalized points; the export/`detected_objects` consumers in Workstream C will produce RLE from them server-side.
- Verify by saving a frame with an AI mask in Studio and checking the stored `Annotation.detected_objects` polygon equals the canvas shape (± 1 px in normalized space).

### B4. Auto-load prelabels as editable polygons
- On opening an image that already has `detected_objects` with `mask` (normalized polygon), `LabelCanvas` must render them as the same editable Fabric polygons on mount (mirroring the existing auto-rect rendering for prelabels), not skip them.
- Reuses `BBox.polygon?: [number, number][]` in `types/index.ts` (exists). Add optional `label?: string` and `confidence?: number` if not already present.

**Acceptance criteria (B):**
- An image with AI masks opens in Studio with editable polygons that match the saved `detected_objects`.
- Saving re-persists polygons with the correct class (not `"car"`), and a re-opened saved image shows identical polygons.
- Polygon vertex dragging, re-classification, and deletion all work and persist.

---

## Workstream C — RLE Persistence on Live Save (follow-up B3)

**Outcome:** every live-saved frame with masks stores a compact COCO RLE alongside the polygon, reliably.

### C1. Fix the broken runtime dependency (blocker)
- `requirements.txt:27` already declares `pycocotools>=2.0.7` but the venv lacks it. Actions:
  - `pip install pycocotools>=2.0.7` into the project venv and confirm import.
  - Add a startup health probe in `app/ai/sam_segmenter.py` (or `app/core/config.py` validation) that logs a clear `mask_rle_unavailable` warning once if `pycocotools` is missing — the current silent `""` return masks the failure.
  - **Do not ship a fallback that writes empty strings.** If `pycocotools` is genuinely unavailable at runtime, `_attach_mask_rle` must skip RLE and log once per process, leaving polygons as the persisted mask representation.

### C2. Harden `mask_to_rle`
- Make `mask_to_rle(mask)` fall back to a **scipy-free, dependency-light** encoder is **out of scope** (do not hand-roll RLE). Instead: keep `pycocotools` as the sole encoder, raise a clear `ImportError` (do not return `""`) so callers log properly.
- Add unit tests with a tiny 8×8 mask: RLE encodes, `mask_utils.decode` round-trips to the exact same binary mask, and pixel count (area) matches `mask.sum()`.
- Add a pure helper `polygon_to_mask_rle(polygon, width, height)` in `app/ai/yolo_seg.py` that reuses `_polygon_to_mask` logic (move it from `annotations_live.py` into a shared module, e.g. `app/ai/mask_utils.py`, so live-save and Studio-export use one rasterizer).

### C3. Persist + surface RLE
- In `save_live_annotation`, after `_attach_mask_rle`, include `mask_format: "rle"` + `mask_rle` on each object; keep `mask` polygon too (Studio needs it for editing, Workstream B).
- `ImageRecord.metadata_` gains `has_mask_rle: bool`.
- Document/implement in the export/manifest builder: consumers may prefer `mask_rle` (compact) or `mask` polygon (editable) — both present, marked by `mask_format`.

**Acceptance criteria (C):**
- `pip install` is run; `import pycocotools` succeeds in the venv; startup logs no `mask_rle_unavailable`.
- Saving a live frame with a mask stores a valid, decodeable `mask_rle` in `detected_objects`; round-trip pixel-identical to the polygon.
- Test: `tests/test_annotations_live.py` verifies RLE present + decodes to the same area as the polygon rasterization; `tests/test_mask_utils.py` covers `polygon_to_mask_rle`.
- No silent `""` RLE anywhere.

---

## Workstream D — On-Device (Browser) YOLOv8-seg Inference (follow-up D)

**Outcome:** live annotation and AI-assist keep working (segmentation included) when the backend is unreachable or prelabel is degraded, by running YOLOv8-seg in the browser via onnxruntime-web. Server-first; on-device is the fallback.

### D1. Port the decoder (`yoloSeg.ts`)
- New `frontend/src/ai/yoloSeg.ts` implementing the same post-processing as `app/ai/yolo_seg.py`:
  - Parse output0 `[1,116,8400]` = `4 box + 80 classes + 32 mask coefficients` (COCO-80, class offset 4) — confirm against `SEG_CLASS_NAMES`/server config so class indices match server taxonomy.
  - Confidence = max class score; filter `>= conf_thres` (default 0.35, matching `confidence_threshold`); class = argmax.
  - Boxes: `cx,cy,w,h` center format → `xyxy` in 640×640 letterbox space → undo letterbox padding/scale to full frame.
  - NMS (IoU 0.45) exactly as the server does.
  - Proto masks: `sigmoid(tensordot(mask_coeffs, output1[0]) / proto_stride)` resized to box size, threshold 0.5, then `cv2`-equivalent polygon extraction → normalize to 0..1. (Use a tiny pure-JS marching-squares or the same `RLE`-based contour approach server-side uses; no `opencv.js` dependency.)
  - Return `BBox[]` with `polygon`, `className`, `confidence`, `mask_format: "polygon"`.
- Expose `detectAllSeg(imageData: ImageData | HTMLCanvasElement): Promise<BBox[]>` that reuses `onnxManager`'s `getModel('yolov8n_seg')` (already registered + warmed).

### D2. Wire into `useAIAssist.ts` (server-first)
- `aiDetectAll()` currently prefers the server prelabel API. Add the fallback chain:
  1. online + server reachable → existing prelabel API (`prelabel.py`), unchanged;
  2. server error/timeout OR `navigator.onLine === false` → browser `detectAllSeg` with the current canvas pixels;
  3. neither available → existing cls-grid heuristic as last resort.
- Surface which engine ran (`engine: "server" | "browser" | "grid"`) on each returned box so the UI can show a subtle badge in AI-assist mode.
- Warm the seg model during `initModels` idle time only if memory allows (keep the existing `yolov8n_seg` registry entry; do not load it eagerly on every page).

### D3. Live camera fallback (optional, gated by flag)
- If `VITE_ENABLE_LIVE_ONDEVICE_SEG` is set, allow `/live-annotate` to run a degraded on-device loop when the WS is down (2 fps, browser NMS, no tracking): overlay receives the same `LiveAnnotation[]` shape. Tracking stays server-side only — out of scope to port.

**Acceptance criteria (D):**
- `yoloSeg.ts` pure functions (NMS, box decode, proto-mask decode, letterbox undo) have Vitest coverage using synthetic small tensors (e.g. a hand-built 116×2 tensor) plus one golden test generated from the server model output.
- With the backend stopped, `aiDetectAll` on an upload image returns class+box+mask polygons from the browser and renders them identically to server output for the same test image (≤ 2% IoU delta).
- `engine` field surfaces correctly; no eager memory blowup on normal loads.

---

## Workstream E — 3D Bounding Boxes ("when applicable")

**Outcome:** for the object classes where a monocular estimate is honest — vehicles and people — the live overlay, saved annotations, and Studio persist a **pseudo-3D cuboid** (8 projected corners, dimensions L×W×H in meters, distance in meters). Other classes (plants, road surfaces) and unsupported engines are untouched. **Constraint and honesty rule:** 2D single-frame images carry no true 3D; these are *estimates* under a fixed camera model, always labeled as such.

### E1. Backend: `app/ai/mono_3d.py`
- New module with pure, testable functions:
  - `estimate_3d(bbox_xyxy, class_name, depth_map=None, image_shape=None, intrinsics=None) -> dict | None`
    - Distance: median depth at the bbox center window if `depth_map` given; else pinhole-height heuristic `distance = (class_prior_height_m * fy) / bbox_height_px`.
    - Class priors (meters): person 1.7, car 1.5, bus 3.0, truck 2.8, motorcycle 1.2, bicycle 1.0. `_3D_CLASSES = {person, car, bus, truck, motorcycle, bicycle}` + taxonomy aliases (`pedestrian`, `vehicle` variants). Return `None` for any other class ("when applicable" gate).
    - Intrinsics: default pinhole with horizontal FOV 60° → `fx = (W/2) / tan(30°)`, `fy = fx`, `cx = W/2`, `cy = H/2`; overridable via `settings.CAMERA_FOV_DEG` and an optional `CAMERA_INTRINSICS` JSON.
    - Dimensions: class-prior L×W×H (person 0.5×0.5×1.7, car 4.5×1.9×1.5, bus 11.0×2.5×3.0, truck 8.0×2.5×2.8, motorcycle 2.0×0.8×1.2, bicycle 1.7×0.6×1.0).
    - Yaw: fixed 0 for MVP (object facing the camera) — yaw-from-gradient is out of scope (E5). Build 8 3D corners `(±L/2, ±W/2, 0 | −H)` about the object center, rotate by yaw, project: `x2d = fx*X/Z + cx`, `y2d = fy*Y/Z + cy`.
    - Return `{ corners2d: [[x,y],×8] (normalized 0..1), dimensions_m: {length,width,height}, distance_m, yaw_rad }`.
  - `attach_3d_boxes(tracked, image_bytes) -> None` — for each tracked object whose class ∈ `_3D_CLASSES`, attach `bbox_3d`; skip silently (no `bbox_3d` key) otherwise. Uses a depth map when the estimator is available, else the heuristic.
- **Constraint:** run **after** tracking (associates per track_id) and after mask attach; 3D uses the same analyzed frame, so corners are already in mirrored coords when mirrored — no flip needed server-side (invariant holds).

### E2. Optional monocular depth (improve, don't block)
- `app/ai/depth_estimator.py`: lazy singleton `get_depth_estimator()` mirroring `get_sam_segmenter()`/`get_yolo_seg_segmenter()`. Model: `Depth-Anything-V2-Small` ONNX (`frontend/public/models/depth_anything_v2_vits.onnx` if bundled, or `DEPTH_MODEL_PATH` env), output single-channel normalized inverse depth at input resolution.
- Depth is a **quality boost**, never a hard dependency: unavailable → E1 heuristic path with `depth_available: false` in the payload.

### E3. WebSocket + persistence
- `app/api/ws_annotation.py`: after `attach_3d_boxes`, each tracked object may carry `bbox_3d`. Add to the WS annotation shape and to `types/index.ts` (`LiveAnnotation.bbox_3d?: { corners2d: [number,number][]; dimensions_m: {length,width,height}; distance_m: number; yaw_rad: number }`).
- `app/api/annotations_live.py`: accept optional `bbox_3d` form field (JSON array aligned with `annotations`), merge into objects; `_attach_mask_rle` skips objects without masks (already does). Persist `bbox_3d` inside `detected_objects` (no schema migration — JSONB).
- Offline queue (`useOfflineSync.ts`) already stores the WS payload; include `bbox_3d` in the queued frame.

### E4. Overlay rendering
- `AnnotationOverlay.tsx`: add `displayMode` values `"boxes" | "masks" | "both" | "3d" | "all"` (i18n keys in `en.json` + `ny.json`). The **3D / All** modes are only offered when the active model_type is `object_detection` (vehicles/people).
- Render a cuboid per `bbox_3d`: the 12 edges between the 8 projected corners (indices: 0-1,1-3,3-2,2-0,4-5,5-7,7-6,6-4,0-4,1-5,2-6,3-7), top face (4,5,7,6) filled at `fillOpacity 0.2` in the class color, and a label chip: `car · 12.3 m · 4.5×1.9×1.5 m`.
- Orientation invariant: `corners2d` are normalized coords in the analyzed frame, drawn un-flipped exactly like boxes; `flipCuboidX` (A4) exists for any debug/depth probe only.
- In `"3d"` mode, hide 2D boxes but keep masks only if they belong to a 3D class; `"all"` shows everything.

### E5. Honest limitations (must be documented in code + UI copy)
- Single 2D frame, fixed intrinsics, no LiDAR/multi-view → distance and dimensions are **estimates**; yaw fixed at 0 (objects assumed facing camera). No occlusion reasoning; cuboids may overlap in depth.
- 3D is a companion of 2D annotations, not a replacement; consumers must treat `distance_m` as approximate (indicate `±` ~20%).
- Not applied to segmentation-only models (`road_segmentation`, `agri_*`) — those classes are out of the `_3D_CLASSES` gate.

**Acceptance criteria (E):**
- `tests/test_mono_3d.py`: for a known bbox + focal, `distance_m` from the height heuristic is exact; projected `corners2d` of a centered cuboid land within the 2D bbox bounds and are axis-aligned at yaw 0; `None` returned for non-3D classes; depth-map path uses median depth.
- `tests/test_annotations_live.py`: `bbox_3d` round-trips into `detected_objects` with and without `dataset_id`.
- WS live test (`tests/test_live_annotation_ws.py`): tracked vehicle objects include `bbox_3d` with 8 corners; tracked plant/road objects omit it.
- Overlay renders cuboids in `"3d"`/`"all"`; Vitest asserts 12 edges emitted and top-face fill present; mirrored preview keeps cuboid alignment (probe test from A1/A3).
- UI copy + inline docs state estimates are approximate.

---

## Technical Constraints (all workstreams)

- **Backend pattern parity:** new lazy singletons must follow `get_sam_segmenter()` / `get_yolo_seg_segmenter()` (process-wide lock, env-configurable path, graceful `None`).
- **No schema migrations:** `detected_objects` is JSONB; all new fields are additive.
- **i18n:** every new string (display modes, "3D", "≈ distance", badges) lands in **both** `en.json` and `ny.json`.
- **No new heavy runtime deps:** browser side must not require `opencv.js` (pure-TS polygon extraction); server side adds only `pycocotools` (already declared) and optionally `onnxruntime` (already present) for depth.
- **Performance:** live WS must stay ≤ ~2 fps latency budget; caps: mask polygon ≤ 32 points, 3D computed once per tracked object per frame, depth model run at reduced resolution (e.g. 256×256) if enabled.

## File Touch-Points

| Workstream | Backend | Frontend | Tests |
|-----------|---------|----------|-------|
| A | — | `LiveAnnotatePage.tsx`, `AnnotationOverlay.tsx`, `orientation.ts`, new `utils/drawAnnotations.ts` | `orientation.test.ts`, new draw round-trip test |
| B | — | `LabelCanvas.tsx`, `useAIAssist.ts`, `types/index.ts` | Vitest for save round-trip normalize |
| C | `annotations_live.py`, `yolo_seg.py` (+ `app/ai/mask_utils.py`), `sam_segmenter.py`, `requirements.txt` (install), export builder | `types/index.ts` | `test_annotations_live.py`, `test_mask_utils.py` |
| D | — | `ai/yoloSeg.ts`, `ai/onnxManager.ts`, `hooks/useAIAssist.ts` | new `yoloSeg.test.ts` (+ golden from server) |
| E | `app/ai/mono_3d.py`, `app/ai/depth_estimator.py`, `ws_annotation.py`, `annotations_live.py` | `AnnotationOverlay.tsx`, `types/index.ts`, `useOfflineSync.ts`, i18n `en/ny.json` | `test_mono_3d.py`, extend `test_live_annotation_ws.py`, `test_annotations_live.py`, overlay Vitest |

## Definition of Done

- All five workstream acceptance criteria pass; backend pytest suite (existing 28 + new) green; Vitest suite green.
- Live-annotate verified manually: front camera un-mirrored default + mirrored toggle both keep boxes/masks/cuboids aligned; saved frames WYSIWYG with `orientation`, `mask`+`mask_rle`, and `bbox_3d` where applicable.
- Studio verified: AI masks open as editable, correctly-classed polygons and save round-trip cleanly.
- `pip install` executed; no silent `""` RLE; startup logs clean.
- i18n complete (en + ny); no new CSS mirror can be applied to the overlay (asserted).

## Out of Scope

- True 3D reconstruction: LiDAR/camera-LiDAR fusion, multi-view/SfM/stereo depth, yaw estimation from image gradients (fixed yaw=0 for MVP).
- 3D for segmentation-only engines (`road_segmentation`, `agri_crop_classification`, `agri_health_classification`) and non-vehicle/people classes.
- Porting the object tracker to the browser (server-only tracking stays).
- Hand-rolled RLE encoding (pycocotools is the single encoder).
