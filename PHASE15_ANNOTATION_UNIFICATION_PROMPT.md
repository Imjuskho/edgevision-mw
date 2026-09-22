# EdgeVision-MW — Phase 15 Development Prompt
## Annotation Unification: One Workspace, Shared Primitives, Coordinate Parity

**Date:** 12 August 2026  
**Context:** Phase 14 unified the **static bbox shell** (`AnnotateWorkspace` + `ImageSidebar` in `AnnotationPage`). Five parallel annotation UIs still exist (static bbox, live video, road segment, TurboReview, upload capture). `LabelCanvas` was removed in Phase 12 without full feature parity. Phase 15 consolidates layout, design-system controls, and coordinate helpers — then restores polygon/mask editing on the primary canvas.

**Design invariant (carried over):** The frame sent to inference, saved to storage, and shown in the overlay must match. All annotation coordinates (bbox, polygon, mask, cuboid corners) are normalized to the **analyzed frame** space.

---

## Verified Current State (12 Aug 2026)

| Surface | Shell | Canvas | AI / Save | DS primitives |
|---------|-------|--------|-----------|---------------|
| `AnnotationPage` | `AnnotateWorkspace` | `AnnotationCanvas` (bbox) | `useAIAssist` + `useResilientSave` | Yes |
| `SegmentPage` | Custom `segment-*` layout | Fabric polygons | `useRoadSegmentation` | No (legacy `btn`) |
| `LiveAnnotatePage` | Standalone | Video + SVG overlay | `useLiveAnnotation` + frame queue | No |
| `TurboReview` | Own layout | DOM refine overlay | Session review submit | Partial |
| `UploadPage` capture | Inline | None (upload only) | Upload API | Partial |

**Shared today:** `drawAnnotations.ts`, `orientation.ts`, `captureFrame.ts` — but not wired through all surfaces.

---

## Workstream A — Extend `AnnotateWorkspace` (do first)

**Goal:** One layout contract for static + segment modes before touching canvas engines.

- Extend `AnnotateWorkspace` props:
  - `workspaceMode: "bbox" | "segment"`
  - `inspector?: ReactNode` — replaces default class palette when provided
  - `hideAutoLabel?: boolean`, `hideLabelSelector?: boolean`
  - Optional props for modes that don't use bbox AI (`onAutoLabel`, load states)
- Migrate **`SegmentPage`** into `AnnotateWorkspace`:
  - Remove duplicate `ImageSidebar` + legacy toolbar
  - Put `RoadSegPanel` in `inspector` slot
  - Road class `<select>` in `toolbarExtra` via `ui/Select`
  - i18n all hardcoded segment strings (en + ny)
- CSS: segment canvas uses `annotate-canvas-wrap`; deprecate duplicate `segment-toolbar` rules where redundant

**Acceptance:** Segment route visually matches annotate route (sidebar, toolbar, inspector); no duplicate sidebar wiring; typecheck + build green.

---

## Workstream B — Polygon draw on primary canvas

**Goal:** Restore LabelCanvas polygon capability on the main studio path.

- Extract shared **`FabricPolygonManager`** usage from `SegmentPage` into `AnnotationCanvas` (or a thin `AnnotateCanvas` wrapper)
- Tool toggle: bbox | polygon in workspace toolbar
- Save round-trip: normalized polygon in `human_labels`; class from `LabelSelector`
- Load existing `detected_objects[].mask` as editable polygons on mount (parity with live annotate)
- Vitest: normalize/denormalize polygon coords; save payload shape

**Acceptance:** Annotator can draw polygons on `/datasets/:id/annotate`; reload preserves shapes; bbox mode unchanged.

---

## Workstream C — Live annotate into the shell

**Goal:** Live capture uses the same chrome as static annotate.

- Wrap `LiveAnnotatePage` body in `AnnotateWorkspace` variant (`workspaceMode: "live"`) or extract `LiveAnnotateToolbar` from shared `ui/*`
- Replace legacy `btn` / native `<select>` with `Button`, `Select`, `Badge`
- Reuse taxonomy palette where model is `object_detection`
- Keep video + `AnnotationOverlay` as `children`; preserve mirror/orientation invariants

**Acceptance:** Live page matches design system; display/model controls use tokens; no overlay CSS mirror regression.

---

## Workstream D — Shared coordinate layer

**Goal:** Stop drift between Fabric, SVG, and TurboReview overlays.

- Centralize in `utils/drawAnnotations.ts` (or `utils/annotationCoords.ts`):
  - `normalizedToCanvas`, `canvasToNormalized`, `bboxToOverlay`, `maskToSvgPoints` (already partial)
- Consumers: `AnnotationCanvas`, `AnnotationOverlay`, `TurboReview`, `ReviewImagePreview`
- Document analyzed-frame contract in file header + one Vitest round-trip suite

**Acceptance:** Single import path for coord transforms; round-trip tests green; no behavior change on live overlay.

---

## Workstream E — TurboReview ↔ studio handoff

**Goal:** QA can jump from fast review into full studio on the same image.

- TurboReview row action: **Open in studio** → navigate to annotate route at image index
- Preload detections from review queue into canvas state
- Optional: review mode tab inside workspace (defer if scope-heavy)

**Acceptance:** Click through from `/review/fast` to annotate with boxes/masks visible.

---

## Workstream F — CSS + smoke harness

- Merge overlapping `annotate-*` / `segment-*` / `live-annotate-*` rules where safe
- Fix `test_websocket_drops_concurrent_frame` for latest-frame queue (smoke harness completion)
- Inline-style budget: keep ≤ 20 (`npm run check:inline-styles`)

---

## Technical Constraints

- **No schema migrations** unless refine/handoff requires additive JSONB only
- **i18n:** all new strings in `en.json` and `ny.json`; run `sync-i18n.mjs`
- **Phase 9–11 invariants:** mirror WYSIWYG, no overlay CSS flip, normalized coords
- **Minimize scope per PR slice:** A → B → C is the preferred merge order

## Definition of Done (Phase 15)

1. Segment + static annotate share `AnnotateWorkspace` shell (A)
2. Polygon draw + mask load on primary annotate path (B)
3. Live annotate uses design-system toolbar (C)
4. Shared coord helpers consumed by ≥3 surfaces (D)
5. TurboReview → studio navigation works (E)
6. `typecheck`, Vitest, pytest (incl. WS test fix), inline-style gate green

## Out of Scope

- New ONNX models or training pipeline changes
- Full TurboReview fold-in (optional E tab)
- GPU inference / live perf (separate ops pass)
