# Live Annotation System — Spec Audit

**Last updated:** 2026-08-16  
**Spec source:** Live Annotation System Master Development Spec (Parts A–G)  
**Codebase:** `edgevision-mw`

This document tracks implementation status against the master spec. Update it when completing spec milestones.

---

## Executive Summary

**Effective position:** Steps 1–7 now substantially complete. Sprint 1 (smoothing + ReID + confusion eval), Sprint 2 (plate de-ID), Sprint 3 (event layer) landed previously; **Sprint 4 (road seg MVP + metric depth + road scene endpoint) and Sprint 5 (Cityscapes/KITTI exporters + push alerting) landed in this pass**.

The strongest integrated slice is the live perception → event → save → export pipeline:

```
Browser (useLiveAnnotation.ts) → WS /ws/annotate/live → live_inference.py
  → YOLO-seg + ByteTrack + metric/relative depth + mono_3d → client
Event layer → rules engine + dwell/trajectory state machine + frame ring buffer
  → auto-save clip (annotations_live.py) + PerceptionEvent rows
  → alert dispatch (webhook/sms/push channels) → export_builder.py (COCO/YOLO/VOC/KITTI/Cityscapes)
```

---

## Part-by-Part Status

| Part | Status | Summary |
|------|--------|---------|
| **A — Perception** | Mostly done | ByteTrack + smoothing + ReID + dwell/trajectory events done; **metric depth done** (flat-ground pinhole, `metric_depth.py`); class retrain, INT8 quant missing |
| **B — Road Seg** | MVP done | Defect/surface instance seg + **semantic drivable/hazard/boundary scene analysis** (`road_semantic.py`) + road-edge metric distance (`/road/scene`) |
| **C — Product** | Mostly done | Manual save + rule-based events + auto-save clip done (Sprint 3); **push alerting done (Sprint 5)** — webhook/sms/push channels |
| **D — Infrastructure** | Partial | Face + plate blur, model registry, Prometheus, perception event log; no weather eval |
| **E — Monetization** | Mostly done | Consent + QA + COCO/YOLO/VOC exports; **Cityscapes + KITTI exports done (Sprint 5)**; image zip bundling not yet implemented |
| **F — Frontier** | Missing | FL, synthetic engine, trajectory, anomaly, 3D recon |
| **G — Sequencing** | Steps 1–7 done | Smoothing/ReID/confusion eval, consent/de-ID, tracking + events, road seg MVP, metric depth, QA + exports, capture + alerting all landed; retrain pipeline still missing |

---

## Part A — Core Perception

### A.1 Object Tracking — PARTIAL

| Item | Status | Location |
|------|--------|----------|
| ByteTrack | Done | `app/ai/object_tracker.py` |
| Live WS integration | Done | `app/api/ws_annotation.py`, `app/ai/live_inference.py` |
| CLIP ReID in live path | Done (Sprint 1) | `live_inference.py` passes `image=` to tracker |
| Dwell/trajectory events | Done (Sprint 3) | `app/ai/events.py` — dwell/presence/confidence-drop/distance rules on ByteTrack IDs |

### A.2 Temporal Confidence Smoothing — DONE (Sprint 1)

- Rolling window (default 8 frames) per track in `object_tracker.py`
- Hysteresis: `alert_on_threshold=0.65`, `alert_off_threshold=0.45`
- Live annotations export `confidence` (smoothed), `raw_confidence`, `alert_active`

### A.3 Metric Depth — DONE (Sprint 4)

- **`app/ai/metric_depth.py`** — flat-ground pinhole calibration: `z = (h·f) / (row − horizon)`
- Defaults: `CameraCalibration(height_m=1.5, focal_length_px=700.0, horizon_fraction=0.35)`
- `attach_metric_depth` adds `distance_m`, `distance_quality` (`metric_ground_plane` / `below_horizon_unknown`), `depth_units="meters"` per det (contact row = `y2·h − 1`)
- `mono_3d.estimate_3d` uses metric depth for z when present (`limitation="metric_depth_ground_plane"`); falls back to relative depth ONNX otherwise
- Live path (`live_inference.attach_depth_boxes`) computes metric depth before 3D boxes; annotations carry `distance_m`/`distance_quality`
- `close_approach` DISTANCE rule (`distance_m_max=3.0`) now functional on real metric distance
- Tests: `tests/test_metric_depth.py` (12)

### A.4 Class Confusion Cleanup — PARTIAL (Sprint 1)

- Taxonomy remap: `yolo_seg.py` (`person`→`pedestrian_roadside`, `car`→`car_private`)
- Confusion eval tooling: `app/ai/class_confusion.py`, `scripts/eval_class_confusion.py`
- Retrain / hard-negative mining pipeline: Missing

### A.5 Edge Optimization — PARTIAL

- ONNX Runtime (server + browser): Done
- INT8 quantization / embedded benchmarks: Missing

---

## Part B — Road Segmentation

**Exists:** Road defect/surface instance segmenter (`road_segmenter.py`, `road.py`, `useRoadSegmentation.ts`).

**Sprint 4 additions:**
- **Semantic scene analysis (`app/ai/road_semantic.py`)** — drivable ratio from drivable classes {good_road, dust_road, gravel_road, road_marking}; hazard instances (pothole/crack) with metric distance via `metric_depth_map`; sidewalk/curb geometric boundary heuristics (`method="geometric_boundary"`); road boundary continuity + `road_edge_distance_m` (quality `metric_ground_plane`/`calibration_ground_plane`/`road_continuous`)
- **`POST /api/v1/road/scene`** — image_id + calibration (`camera_height_m`, `focal_length_px`, `horizon_fraction`) → `RoadSceneResponse` (drivable_ratio, hazards, sidewalk/curb regions, road_edge_distance_m, surface_type)
- Tests: `tests/test_road_semantic.py` (12), `tests/test_road_scene_api.py` (4)

**Missing for spec:** shared detection+seg backbone; drivable class retrain; full ADAS drivable-area mask (current sidewalk/curb are geometric heuristics, not model classes).

---

## Part C — Product Architecture

| Item | Status |
|------|--------|
| Manual Save Frame | Done |
| Auto trigger → buffer → clip | Done (Sprint 3) — `FrameRingBuffer` pre/post frames, auto-save on rule trigger |
| Rules engine | Done (Sprint 3) — dwell, presence, confidence-drop, distance; time-of-day + cooldown; ADMIN-configurable via `/annotations/event-rules` |
| On-device inference | Done |
| Cloud persistence | Done |
| Multi-camera search | Missing |
| Perception alerting | Done (Sprint 5) — `AlertChannel` table (webhook/sms/push), `app/services/alerts.py`, ADMIN CRUD `/annotations/alert-channels`, `EventRule.alert` flag; WS dispatch on alert-enabled rule fire (webhook POSTs envelope; sms/push adapters structured-log stubs pending provider creds) |

---

## Part D — Supporting Infrastructure

| Item | Status |
|------|--------|
| Face de-ID on save | Done (`face_privacy.py` + `pii_redaction.py`) |
| License plate de-ID | Done (Sprint 2) — `plate_privacy.py` (LPD-YuNet) + unified `pii_redaction.py` |
| Model versioning | Partial (`model_registry.py`) |
| Evaluation harness | Partial (pytest; no day/night/weather benchmark) |
| Structured event logs | Partial — perception events persisted (`perception_events` table) + `ws_annotate_events_total` Prometheus counter |

---

## Part E — Data Monetization

| Item | Status |
|------|--------|
| Consent ledger | Done |
| Annotation QA / IAA | Done |
| COCO/YOLO exports | Done |
| Cityscapes / KITTI exports | Done (Sprint 5) — `export_builder.py` `_build_kitti_txt` (per-image `# filename` blocks, 3D bbox fields from `bbox_3d`) + `_build_cityscapes_json` (gtFine-style bundle, 1920×1080, `instanceId`); previews via `_preview_kitti`/`_preview_cityscapes` |
| Plate de-ID before export | Partial — `redact_export_image_bytes()` hook ready; image zip bundling not yet implemented |
| Dataset tiering / licensing UI | Partial |

---

## Part F — Frontier Capabilities

All missing: federated learning, synthetic data engine, trajectory prediction, open-set anomaly detection, living 3D reconstruction.

---

## Part G — Master Sequencing

| Step | Priority | Status |
|------|----------|--------|
| 1 | Class confusion + temporal smoothing | **Partial** — smoothing + eval done; retrain missing |
| 2 | Legal/consent + de-ID | Consent done; **plate blur done (Sprint 2)** |
| 3 | Object tracking | ByteTrack done; **event layer done (Sprint 3)** |
| 4 | Road seg MVP | **Done (Sprint 4)** — defect seg + semantic drivable/hazard scene + road-edge distance (`/road/scene`) |
| 5 | Metric depth | **Done (Sprint 4)** — flat-ground pinhole calibration + live depth chips |
| 6 | QA + exports | QA done; **Cityscapes/KITTI done (Sprint 5)** |
| 7 | Event capture + alerting | **Rules + auto-save clip done (Sprint 3)**; **push alerting done (Sprint 5)** |
| 8–15 | Scale-out + frontier | Not started |

---

## Sprint 5 Deliverables (2026-08-16)

1. **Export formats** — `SUPPORTED_FORMATS` now `(COCO, YOLO, PASCAL_VOC, KITTI, CITYSCAPES)`; `_kitti_line` emits `type truncated occluded alpha x1 y1 x2 y2 h w l x y z rotation_y` (fills 3D fields from `bbox_3d` when present), `_build_kitti_txt` groups by `# filename`; `_build_cityscapes_json` emits a gtFine-style JSON bundle (1920×1080, `instanceId` counter); previews for both formats (`_preview_kitti`, `_preview_cityscapes`)
2. **Push alerting** — `AlertChannel` model (Alembic `0021`): `channel_type` webhook|sms|push, name, `config` JSONB, `enabled`, tenant scoping; `app/services/alerts.py` CRUD + `dispatch_event_alert` with adapter registry (webhook = HTTP POST envelope via httpx; sms/push = structured-log stubs); ADMIN endpoints GET/POST/PATCH/DELETE `/annotations/alert-channels`
3. **Rule alert flag** — `EventRule.alert` (defaults True for `dwell_pedestrian_roadside`, `dwell_vehicle`, `close_approach`); serialized through `to_dict`/`from_dict`/rules endpoints
4. **WS dispatch wiring** — on alert-enabled rule fire, `ws_annotation.py` opens a short-lived session and dispatches the alert (never blocks streaming); failures logged, never raised
5. **Frontend** — live event feed shows metric depth chip (`· 2.4m`) from `details.distance_m`; `LiveEvent.details` added to `useLiveAnnotation.ts`
6. **Tests** — `tests/test_alerts_api.py` (10): channel CRUD + authz, dispatch webhook delivery/failure via `httpx.MockTransport`, sms/push stubs, disabled/no-channel no-ops, `EventRule.alert` round-trip

---

## Sprint 4 Deliverables (2026-08-16)

1. **Metric depth** — `app/ai/metric_depth.py` (`CameraCalibration`, `ground_plane_distance_m`, `metric_depth_map`, `metric_distance_at_bbox`, `attach_metric_depth`); wired into `live_inference.attach_depth_boxes` + `mono_3d.estimate_3d` (z from metric depth, `limitation="metric_depth_ground_plane"`)
2. **Road semantic scene** — `app/ai/road_semantic.py` (`decode_mask_rle` via pycocotools, `RoadSceneAnalysis`, `analyze_road_scene`) → drivable ratio, hazards w/ distance, sidewalk/curb heuristics, road-edge distance
3. **`POST /road/scene`** — `app/api/road.py` + `app/schemas/road.py` (`RoadSceneRequest/Hazard/SidewalkRegion/RoadScene/Response`); fetches image from MinIO, runs segmenter, builds metric map from calibration
4. **Tests** — `tests/test_metric_depth.py` (12), `tests/test_road_semantic.py` (12), `tests/test_road_scene_api.py` (4)

---

## Sprint 3 Deliverables (2026-08-16)

1. Event/rules engine (`app/ai/events.py`) — dwell-time + trajectory state machine on ByteTrack IDs, presence, confidence-drop, distance-threshold rules; time-of-day windows, per-rule cooldown, taxonomy-aware matching
2. Configurable rules persistence — `workspace_settings.operational_json` under `perception_event_rules`; GET/PUT `/annotations/event-rules` (ADMIN)
3. Pre/post frame buffering — `FrameRingBuffer` (24 frames); auto-save clip on rule trigger via `save_live_capture` (`capture_reason="auto_event"`, `event_id` link)
4. Perception events persisted — `perception_events` table (Alembic `0020`), `GET /annotations/events` (paginated), `record_perception_event`
5. WS integration — `events`/`auto_save`/`dataset_id` query params; `{"type":"event"}` + `{"type":"event_saved"}` WS messages; `ws_annotate_events_total` metric
6. Refactor — `save_live_capture` extracted from `annotations_live.py` into `app/services/live_capture.py`
7. Frontend — auto-save toggle + live event feed in `LiveAnnotateInspector`, i18n keys (en/ny), WS message branching in `useLiveAnnotation.ts`
8. Tests — `tests/test_events.py` (19), `tests/test_perception_events_api.py`, WS event/auto-save tests in `test_live_annotation_ws.py`; fixed `test_confidence_smoothing_reduces_flicker` (first detection below high-threshold never created a track)

---

## Sprint 2 Deliverables (2026-08-16)

1. License plate detection + blur (`plate_privacy.py`, `lpd_yunet.py`) using OpenCV Zoo LPD-YuNet ONNX
2. Unified PII redaction pipeline (`pii_redaction.py`) — faces + plates in one call
3. Live save path uses unified redaction (`annotations_live.py`); returns `plates_blurred`, `pii_redacted`
4. Batch auto-label worker redacts faces + plates before MinIO write (`workers/tasks.py`)
5. Export pre-processing hook (`export_builder.redact_export_image_bytes`) + README privacy section
6. PII audit vision spot-check on stored images (`compliance.py`)
7. Tests: `tests/test_pii_redaction.py`

---

## Sprint 1 Deliverables (2026-08-16)

1. Per-track rolling confidence smoothing + alert hysteresis (`object_tracker.py`)
2. ReID enabled in live inference (`live_inference.py` passes frame image to tracker)
3. Class confusion evaluation module + CLI (`class_confusion.py`, `eval_class_confusion.py`)
4. Unit tests: `test_object_tracker.py`, `test_class_confusion.py`

### Usage — confusion eval

```bash
cd edgevision-mw

# Overlap scan (no ground truth)
python scripts/eval_class_confusion.py --images path/to/frames

# With COCO ground truth
python scripts/eval_class_confusion.py --images path/to/images --coco annotations.json --output reports/confusion.json
```

---

## Priority Gaps (next sprints)

1. Class retrain / hard-negative mining pipeline (step 1 remainder) + shared detection/seg backbone + drivable-area model class retrain (removes sidewalk/curb heuristics)
2. SMS/push provider adapters (Twilio/FCM-style) — webhook channel is live; sms/push are structured-log stubs pending credentials
3. Export image zip bundling (`redact_export_image_bytes` hook ready, zip not implemented)
4. Part F frontier capabilities (after 1–7 solid)
