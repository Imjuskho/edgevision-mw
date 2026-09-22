# EdgeVision-MW — Phase 8 Development Prompt
## Road Surface Instance Segmentation — AI-Assist & Automatic Analysis

**Date:** 28 July 2026
**Context:** EdgeVision-MW is a functional AI-powered annotation platform for Lilongwe road-user imagery. Phase 7 (Image Ingestion, Annotator Assignment, QA Review) is complete. The platform currently supports bounding-box object detection with a full 85-class Malawi taxonomy. The backend has stubs for SAM/YOLO/CLIP, while the frontend has real ONNX Runtime Web inference with MobileSAM and YOLOv8n-cls running client-side. The current annotation workflow is entirely bbox-based; polygons exist as an AI-returned format but are not a first-class annotation type.

---

## Goal

Add road surface instance segmentation to EdgeVision-MW so annotators can label road defects and surface types with pixel-precise masks, and the platform can automatically analyse road condition from uploaded imagery.

This introduces a **new annotation paradigm** (polygon/mask instead of bbox), a **new model pipeline** (YOLOv8-seg → ONNX, running both server-side and client-side), and a **new road surface taxonomy** that lives alongside the existing 85-class road-user taxonomy.

---

## Scope

### 1. Road Surface Taxonomy (Phase 8 Initial Classes)

A focused set of road surface classes, separate from the existing road-user taxonomy, initial release (extensible):

| Class ID | Name | Description |
|----------|------|-------------|
| 0 | good_road | Smooth paved/asphalt surface in good condition |
| 1 | pothole | Cavity or hole in the road surface |
| 2 | crack | Linear fracture (single or crocodile cracking) |
| 3 | dust_road | Unpaved dirt/dust surface |
| 4 | gravel_road | Unpaved surface with loose gravel/stones |
| 5 | road_marking | Painted lane lines, crosswalks, arrows |
| 6 | shoulder | Road edge / verge (non-carriageway) |

**Design notes:**
- Classes are mutually exclusive per-mask (instances don't overlap)
- "good_road" covers any paved area that is NOT pothole/crack/marking/shoulder
- Add `surface_type` attribute tag for override cases (e.g., a pothole ON a dust road)
- The taxonomy is versioned and stored in a new `app/models/road_taxonomy.py` + frontend `frontend/src/constants/roadTaxonomy.ts`

**Extensibility:** The model should be trained with room to add classes (e.g., "speed bump", "standing water", "rut", "failed patch") in Phase 8.1 without retraining from scratch.

---

### 2. Model Pipeline — YOLOv8-seg

#### Model Selection: YOLOv8n-seg / YOLOv8s-seg
- **Why:** Native instance segmentation, easy ONNX export, dual browser/server, good accuracy/speed tradeoff, already in the project's mental model (YOLOv8n-cls exists)
- **Variants:** YOLOv8n-seg (nano, fastest) for client-side, YOLOv8s-seg (small) for server-side batch inference
- **Output:** Per-instance: `{class_id, confidence, bbox [x,y,w,h], mask (binary), polygon}`

#### Training Pipeline
1. **Data format:** COCO JSON with polygon annotations (compatible with Ultralytics training format)
2. **Annotation tool:** Existing LabelCanvas with enhanced polygon drawing tool (see Frontend Workstream)
3. **Initial training:** Seed with public datasets (BDD100K, Mapillary Vistas, Surreal — road surface subset) + manually annotate 500 Lilongwe images
4. **Augmentation:** Mosaic, mixup, random perspective, brightness/contrast (dust roads vary hugely in lighting)
5. **Validation:** Per-class mAP@50, mAP@50:95, inference latency (target: <50ms on GPU, <200ms on CPU, <500ms browser)
6. **Export:** `torch → ONNX` with dynamic batch size, FP16 for server, FP32/INT8 for browser

#### Model Serving

**Backend (FastAPI):**
- New `app/ai/road_segmenter.py` — class `RoadSegmenter` that loads ONNX model, runs inference, returns `list[InstanceMask]`
- `InstanceMask` schema: `{class_id, class_name, confidence, bbox, mask (RLE), polygon (simplified)}`
- Lazy-loaded singleton, similar pattern to existing stubs but with real inference
- Config paths: `ROAD_SEG_MODEL_PATH` in `app/core/config.py`
- Batch inference endpoint for auto-labeling (used by Celery worker)

**Frontend (ONNX Runtime Web):**
- Add YOLOv8-seg ONNX model to the frontend model registry in `onnxManager.ts`
- Model files served from `/models/yolov8n-seg.onnx` (FP32) — target ~20-25MB
- Implement `segmentImage()` in `useAIAssist.ts` (or a new `useRoadSegmentation.ts` hook):
  - Run encoder → get masks → post-process (NMS, mask thresholding) → convert to Fabric.js polygons
- Fallback: if frontend inference is too slow on low-end devices, call backend API instead

---

### 3. Backend Workstream

#### 3.1 Road Surface Model & Schema

**`app/models/road_annotation.py`:**
```python
class RoadAnnotation(Base):
    """Stores instance segmentation annotations for road surface."""
    id: uuid.UUID (PK)
    annotation_id: uuid.UUID (FK → annotations.id, one-to-one)
    surface_type: str  # "paved" | "unpaved" | "mixed"
    instances: JSONB  # [{class_id, class_name, confidence, bbox, mask_rle, polygon}]
    model_version: str  # e.g. "yolov8n-seg-v1"
    auto_generated: bool
    reviewed: bool
    created_at, updated_at
```

- `RoadAnnotation` links 1:1 to the existing `Annotation` record (one per image)
- The existing `Annotation.detected_objects` is NOT repurposed — this is a separate table for surface analysis
- An Alembic migration creates the new table

**`app/schemas/road.py`:**
```python
class InstanceMask(BaseModel):
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]  # [x, y, w, h] normalized
    mask_rle: str  # Run-length encoded binary mask
    polygon: list[tuple[float, float]] | None  # Simplified polygon (for frontend rendering)

class RoadSegmentationResult(BaseModel):
    image_id: uuid.UUID
    instances: list[InstanceMask]
    surface_type: str
    model_version: str
    latency_ms: float
```

**`app/models/road_taxonomy.py`:**
```python
ROAD_SURFACE_CLASSES = {
    0: {"name": "good_road", "color": "#4CAF50"},
    1: {"name": "pothole", "color": "#F44336"},
    2: {"name": "crack", "color": "#FF9800"},
    3: {"name": "dust_road", "color": "#795548"},
    4: {"name": "gravel_road", "color": "#9E9E9E"},
    5: {"name": "road_marking", "color": "#2196F3"},
    6: {"name": "shoulder", "color": "#8BC34A"},
}
```

#### 3.2 AI Inference — `app/ai/road_segmenter.py`

Full replacement for the existing stubs in this domain:

```python
class RoadSegmenter:
    def __init__(self, model_path: str, device: str = "cpu"):
        # Load ONNX model with onnxruntime
        # Warm up with dummy input

    def segment(self, image: np.ndarray, conf_threshold=0.35, iou_threshold=0.45) -> list[InstanceMask]:
        # Preprocess: resize to 640x640, normalize
        # Run inference
        # Post-process: NMS, mask decoding, mask-to-polygon
        # Return InstanceMask list

    def segment_batch(self, images: list[np.ndarray], ...) -> list[list[InstanceMask]]:
        # Batch inference for efficiency
```

**Post-processing details:**
- Use `skimage.measure.find_contours` for mask-to-polygon (already in `studio_ai.py`)
- RLE encoding using `pycocotools.mask` (add `pycocotools>=2.0.7` to requirements)
- Polygon simplification with `skimage.measure.approximate_polygon` (Douglas-Peucker, epsilon=2.0)

#### 3.3 API Endpoints

**New router: `app/api/road.py`**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/road/segment` | Run segmentation on one image (upload or MinIO ref). Returns InstanceMask list. |
| `POST` | `/api/v1/road/segment/batch` | Batch segment up to 50 images. Returns job_id for async result. |
| `GET` | `/api/v1/road/result/{annotation_id}` | Get stored RoadAnnotation for an annotation. |
| `PATCH` | `/api/v1/road/result/{annotation_id}` | Update/review RoadAnnotation instances (e.g., annotator corrected AI output). |
| `GET` | `/api/v1/road/classes` | Return current road taxonomy class list. |
| `POST` | `/api/v1/road/analyze` | Run full analysis on a dataset: segment all images, aggregate road condition stats. |

**Auto-labeling task (Celery):**
- Extend `app/workers/tasks.py` with `auto_label_road_task`:
  - Triggered by `POST /api/v1/road/segment/batch` or by dataset ingestion hook
  - Runs `RoadSegmenter.segment_batch()` on each image
  - Creates/updates `RoadAnnotation` records
  - Generates dataset-level aggregate: `{total_potholes, good_road_pct, dust_road_pct, avg_crack_density}`

#### 3.4 Dataset-Level Road Analysis

**`app/services/road_analysis.py`:**
```python
def analyze_dataset_road_condition(dataset_id: uuid.UUID) -> RoadConditionReport:
    """Aggregate road surface stats across a dataset."""
    # Total pothole count, density per km
    # Percentage breakdown: good_road vs dust_road vs gravel_road
    # Crack severity score
    # Pothole cluster detection (DBSCAN on pothole centroids)
    # Time-series comparison (if dataset has temporal data)
```

**RoadConditionReport schema:**
```python
class RoadConditionReport(BaseModel):
    dataset_id: uuid.UUID
    total_images: int
    surface_breakdown: dict[str, float]  # {"good_road": 0.45, "pothole": 0.05, ...}
    pothole_count: int
    pothole_density_per_km2: float  # estimated
    crack_severity: Literal["low", "medium", "high"]
    condition_score: float  # 0.0 (worst) to 1.0 (best)
    recommended_action: str | None  # e.g. "Re-gravel Wing Section C"
```

#### 3.5 Tests

- `tests/test_road_segmenter.py` — Unit tests for RoadSegmenter (mock ONNX, test pre/post processing)
- `tests/test_road_api.py` — Integration tests for all new endpoints
- `tests/test_road_analysis.py` — Test aggregation logic
- Target: +25 tests, all passing. Maintain existing test count.

---

### 4. Frontend Workstream

#### 4.1 Polygon Drawing Tool — Full Implementation

The `LabelCanvas.tsx` has a polygon tool button but no drawing logic. This Phase delivers it.

**Polygon drawing in LabelCanvas:**
- Mode: user clicks to place vertices, double-click or Enter to close polygon
- Visual: dashed line connecting vertices, filled polygon with low opacity once closed
- Editing: drag vertices to adjust, Ctrl+click to delete a vertex
- Fabric.js objects: `fabric.Polygon` with custom controls
- Normalization: store as relative coordinates `[[x1,y1], [x2,y2], ...]` (0-1)
- Keyboard: `Escape` cancels current polygon, `Delete` removes selected polygon

**Polygon-to-mask conversion** (for training data export):
- Client-side: rasterize Fabric.js polygon to binary mask (canvas method)
- Server-side: already have `_mask_to_polygon()` — need reverse `polygon_to_mask()`

#### 4.2 Road Segmentation Panel — New Component

**`frontend/src/components/RoadSegPanel/RoadSegPanel.tsx`:**

A side panel (similar to the taxonomy label panel) that:
- Toggles road segmentation mode on/off
- Shows detected instances from AI as a list with confidence scores
- Allows annotator to accept/reject/edit each instance
- Color-coded by class (green=good_road, red=pothole, etc.)
- "Auto-segment" button that triggers AI (frontend if model loaded, else backend API call)
- Shows aggregated stats: "3 potholes detected, 85% good road"

**Road-specific toolbar** with tools:
- `Auto-segment` — run AI on current image
- `Draw polygon` — activate polygon drawing tool
- `Brush mask` — paint mask freehand (future: use SAM point prompt)
- `Erase` — erase parts of a mask
- `Accept all` / `Reject all` — bulk accept/reject AI suggestions

#### 4.3 AI Integration — `useRoadSegmentation.ts`

New hook, similar pattern to `useAIAssist.ts`:

```typescript
interface UseRoadSegmentationReturn {
  // State
  isModelLoaded: boolean;
  isProcessing: boolean;
  progress: number; // 0-100
  instances: InstanceMask[];
  error: string | null;

  // Actions
  loadModel: () => Promise<void>;
  segmentImage: (imageData: ImageData) => Promise<InstanceMask[]>;
  segmentViaApi: (imageId: string) => Promise<InstanceMask[]>;
  acceptInstance: (id: string) => void;
  rejectInstance: (id: string) => void;
  clearInstances: () => void;
}
```

**Inference strategy:**
1. Try client-side first (check `onnxManager.isModelReady('yolov8n_seg')`)
2. If not loaded or too slow, call `POST /api/v1/road/segment`
3. Cache results in IndexedDB (via Dexie, already in project) to avoid re-running

#### 4.4 ONNX Manager Update

**`frontend/src/ai/onnxManager.ts`:**
- Add `yolov8n_seg` to the model registry
- Model files: `/models/yolov8n-seg.onnx` (encoder + decoder combined, ~20-25MB)
- Preload strategy: lazy-load when user enters road segmentation mode (not on app boot)
- Memory: MobileSAM is ~27MB + decoder ~20MB = ~47MB. YOLOv8n-seg is ~20MB. Consider offloading MobileSAM when not in use to free memory.

#### 4.5 New Frontend Routes

| Route | Component | Purpose |
|-------|-----------|---------|
| `/segment/:sessionId` | `SegmentPage.tsx` | Dedicated road segmentation annotation page |
| `/road-analysis/:datasetId` | `RoadAnalysisPage.tsx` | Dataset-level road condition dashboard |
| `/admin/road-taxonomy` | `RoadTaxonomyPage.tsx` | (Admin) Manage road surface classes |

**`SegmentPage.tsx`** — Similar layout to `AnnotationPage.tsx` but:
- Uses `LabelCanvas` in polygon mode by default
- Shows `RoadSegPanel` instead of taxonomy label panel
- Instances stored to new `RoadAnnotation` table via API
- Supports both: "AI Assist" mode (annotator corrects AI output) and "Manual" mode (annotator draws from scratch)

**`RoadAnalysisPage.tsx`** — Dashboard showing:
- Pie chart of surface type breakdown (Recharts, already a dependency)
- Pothole density heatmap overlay (if GPS data available)
- Condition score gauge
- Image grid filtered by surface class ("Show all pothole images")
- Export report button (PDF or CSV)

#### 4.6 Fabric.js Polygon Enhancements

**`frontend/src/components/LabelCanvas/FabricPolygonManager.ts`** (new):
- Custom Fabric.js `Polygon` subclass with:
  - Midpoint handles (for adding vertices)
  - Vertex drag handles
  - Hover highlighting
  - Click-to-select, click-background-to-deselect
- Keyboard shortcuts for polygon editing:
  - `V` = select/move tool
  - `P` = draw polygon tool
  - `Delete/Backspace` = remove selected instance
  - `A` = accept selected AI instance
  - `R` = reject selected AI instance
- Polygon simplification on save (Ramer-Douglas-Peucker to reduce vertex count)

#### 4.7 COCO Export Update

Update the existing COCO export (`app/workers/tasks.py`) to include:
- `segmentation` field in COCO annotations (polygon format) when exporting road segmentation data
- A new export type: `road_segmentation_coco` that exports polygons instead of bboxes
- Dataset-level road analysis attached as metadata

#### 4.8 i18n

All new UI text in `en.json` and `ny.json`:
- `roadSegmentation.*` — panel labels, buttons, tooltips
- `roadClasses.*` — class display names (Chichewa: "Dzenje" for pothole, "Msewu wafumbi" for dust road, etc.)
- `roadAnalysis.*` — dashboard labels
- `polygonTool.*` — drawing instructions, shortcuts

---

### 5. Training & Data Pipeline (DevOps/ML)

#### 5.1 Seed Data

- **Public datasets:** BDD100K (drivable area + lane), Mapillary Vistas (road surface), Surreal (road defects)
- **Lilongwe-specific:** Manually annotate 500 images from existing MinIO storage with polygon masks for the 7 road classes
- **Annotation format:** COCO JSON with `segmentation` as polygon `[[x1,y1,x2,y2,...]]`

#### 5.2 Training Script

**`scripts/train_road_seg.py`:**
```python
# Uses ultralytics YOLOv8-seg
# python scripts/train_road_seg.py --data road_dataset.yaml --model yolov8n-seg.pt --epochs 100 --imgsz 640
```

**`road_dataset.yaml`:**
```yaml
path: /data/road_seg/
train: images/train
val: images/val
nc: 7
names: ['good_road', 'pothole', 'crack', 'dust_road', 'gravel_road', 'road_marking', 'shoulder']
```

#### 5.3 Export to ONNX

```python
from ultralytics import YOLO
model = YOLO('runs/segment/train/weights/best.pt')
model.export(format='onnx', imgsz=640, dynamic=True, simplify=True)
```

- **Server model:** FP16 ONNX (`yolov8s-seg-fp16.onnx`) — ~40MB, runs on CPU/GPU
- **Browser model:** FP32 ONNX (`yolov8n-seg.onnx`) — ~20MB, runs via ONNX Runtime Web, target <500ms on modern laptop
- **INT8 quantized** (optional): ~10MB, target <300ms, for low-end devices

---

### 6. Acceptance Criteria

- [ ] Annotator can draw, edit, and save polygon masks for road surface features on Fabric.js canvas
- [ ] "Auto-segment" button runs YOLOv8-seg inference (frontend or backend) and overlays detected instances as editable polygons
- [ ] Annotator can accept/reject/edit AI-proposed instances
- [ ] Road surface taxonomy (7 classes) is displayed with color coding in the UI
- [ ] Road segmentation annotations are stored in `RoadAnnotation` table, linked 1:1 to `Annotation`
- [ ] Backend `POST /api/v1/road/segment` returns instance masks with RLE + polygon
- [ ] Batch auto-labeling via Celery processes 50 images and creates `RoadAnnotation` records
- [ ] COCO export includes `segmentation` field when exporting road data
- [ ] Dataset-level road analysis dashboard shows surface type breakdown, pothole count, condition score
- [ ] `RoadSegmenter` achieves >0.5 mAP@50 on held-out Lilongwe test set
- [ ] Frontend polygon tool works with keyboard shortcuts and touch input
- [ ] All new endpoints have passing tests (+25 tests)
- [ ] No regressions in existing test suite
- [ ] All new UI strings are i18n-ready (en + ny)
- [ ] Chichewa class names display correctly (Dzenje, Msewu wabwino, Msewu wafumbi, etc.)

---

### 7. Suggested File Touch Points

#### Backend (New + Modified)
| File | Action |
|------|--------|
| `app/ai/road_segmenter.py` | **NEW** — Real ONNX model inference |
| `app/api/road.py` | **NEW** — Road segmentation API router |
| `app/models/road_annotation.py` | **NEW** — RoadAnnotation SQLAlchemy model |
| `app/models/road_taxonomy.py` | **NEW** — Road surface class definitions |
| `app/schemas/road.py` | **NEW** — Pydantic schemas |
| `app/services/road_analysis.py` | **NEW** — Dataset analysis logic |
| `app/api/router.py` | Include new `road` router |
| `app/core/config.py` | Add `ROAD_SEG_MODEL_PATH`, `ROAD_SEG_CONF_THRESHOLD` |
| `app/workers/tasks.py` | Add `auto_label_road_task` |
| `app/workers/celery_app.py` | Register new task |
| `requirements.txt` | Add `pycocotools>=2.0.7` |
| `alembic/versions/` | **NEW** migration for `road_annotations` table |
| `tests/test_road_segmenter.py` | **NEW** |
| `tests/test_road_api.py` | **NEW** |
| `tests/test_road_analysis.py` | **NEW** |

#### Frontend (New + Modified)
| File | Action |
|------|--------|
| `frontend/src/components/RoadSegPanel/RoadSegPanel.tsx` | **NEW** |
| `frontend/src/components/LabelCanvas/FabricPolygonManager.ts` | **NEW** |
| `frontend/src/hooks/useRoadSegmentation.ts` | **NEW** |
| `frontend/src/pages/SegmentPage.tsx` | **NEW** |
| `frontend/src/pages/RoadAnalysisPage.tsx` | **NEW** |
| `frontend/src/pages/RoadTaxonomyPage.tsx` | **NEW** (admin) |
| `frontend/src/constants/roadTaxonomy.ts` | **NEW** |
| `frontend/src/ai/onnxManager.ts` | Add `yolov8n_seg` model |
| `frontend/src/components/LabelCanvas/LabelCanvas.tsx` | Wire polygon drawing tool |
| `frontend/src/App.tsx` | Add new routes |
| `frontend/src/api/road.ts` | **NEW** — API wrappers |
| `frontend/src/i18n/locales/en.json` | New keys |
| `frontend/src/i18n/locales/ny.json` | New keys |
| `frontend/src/types/index.ts` | Add `InstanceMask`, `RoadAnnotation` types |

#### Model & Config
| File | Action |
|------|--------|
| `scripts/train_road_seg.py` | **NEW** training script |
| `road_dataset.yaml` | **NEW** dataset config |
| `yolov8n-seg.onnx` | **NEW** browser model (served from `/models/`) |
| `yolov8s-seg-fp16.onnx` | **NEW** server model (in MinIO or mounted volume) |

---

### 8. Out of Scope (Phase 8+)

- MobileSAM point-prompt refinement for road masks (Phase 8.1)
- GPS-based road condition mapping (Phase 9)
- Integration with the existing Malawian 85-class taxonomy (they remain separate)
- Road degradation time-series analysis (Phase 10)
- Automatic pothole severity grading (depth/width estimation from monocular) (Phase 8.2)
- Heatmap overlay on map view (Phase 9)
- Edge-device deployment of road model on NVIDIA Jetson (Phase 9)

---

### 9. Technical Constraints

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, ONNX Runtime, Celery
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, Fabric.js v6, ONNX Runtime Web, Recharts, react-i18next
- **Model:** YOLOv8-seg → ONNX export. No PyTorch in production (only in training scripts)
- **File storage:** MinIO for images; model files on disk for the backend, served via static route for frontend
- **Database:** PostgreSQL 16 — new `road_annotations` table, no changes to existing tables
- **Auth:** JWT with role claims. Road analysis endpoints require `admin` or `qa` role. Annotation endpoints require `annotator` role.
- **No breaking changes:** Existing bbox annotation, 85-class taxonomy, export, and QA pipelines remain intact
- **Annotation interoperability:** A single image can have both bbox annotations (road-user taxonomy) AND a `RoadAnnotation` (road surface) — they are independent

---

### 10. Dependencies to Add

#### Backend
- `pycocotools>=2.0.7` — RLE encoding/decoding
- No new ML framework in production — ONNX Runtime already there

#### Training Environment (separate from production)
- `ultralytics>=8.3.0` — YOLOv8-seg training
- `torch>=2.3.0` — PyTorch for training
- `torchvision>=0.18.0`

#### Frontend
- No new npm packages — ONNX Runtime Web and Fabric.js already present

---

## Definition of Done for Phase 8

- [ ] Polygon drawing tool is fully functional (create, edit, delete vertices)
- [ ] YOLOv8n-seg model runs client-side ONNX inference, returns editable instances
- [ ] YOLOv8s-seg model runs server-side, serves batch auto-labeling
- [ ] Backend API surface for road segmentation is complete and tested
- [ ] RoadAnnotation table stores per-image instance segmentation data
- [ ] Dataset-level road analysis dashboard is functional
- [ ] COCO export includes segmentation polygons for road data
- [ ] All new endpoints have passing tests (+25 tests minimum)
- [ ] No regressions in existing tests
- [ ] Frontend polygon drawing works on touch devices (tablets used by annotators)
- [ ] All UI text is translated to Chichewa
- [ ] Model achieves viable accuracy (>0.5 mAP@50) on Lilongwe road images
- [ ] Frontend inference completes in <1s on target laptops (8GB RAM, modern CPU)
- [ ] Backend inference completes in <200ms on CPU, <50ms on GPU
