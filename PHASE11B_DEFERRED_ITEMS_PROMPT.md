# EdgeVision-MW — Phase 11B Development Prompt
## Deferred Items: Depth Model Download, TurboReview Refine-Save, Manual Smoke-Test Runbook

**Date:** 12 August 2026
**Context:** Phase 11 (Platform Hardening) shipped five workstreams, all green (pytest 42/53, Vitest 16, typecheck+build pass). Three items were intentionally deferred and are now the sole scope of this phase: (1) fetch the Depth-Anything-V2-Small ONNX artifact so cuboids get depth-grade distance/yaw, (2) wire TurboReview QA refinements (mask-polygon / cuboid-corner vertex edits) to persist through the studio session endpoint, (3) produce the manual smoke-test runbook that walks live annotate → review → export → dedup → offline reconcile.

**Design invariant (carried over):** *The frame sent to inference and the frame saved to storage must always equal the frame the user sees, and annotation coordinates (boxes, polygons, masks, 3D cuboid corners) must always be expressed in the coordinate space of the analyzed frame.* QA refinements persist normalized (0..1) coordinates in the analyzed-frame space, exactly like every other annotation.

---

## Verified Current State (code audit, 12 Aug 2026)

| # | Area | Verified fact | Implication |
|---|------|---------------|-------------|
| 1 | Depth model | `scripts/download_depth_model.sh` exists and is idempotent (checksum-verified via `.sha256` sidecar; re-downloads on mismatch). Download was **aborted mid-transfer** during the previous session → a partial file may exist at `frontend/public/models/depth_anything_v2_vits.onnx` (checksum will fail, script self-heals). `README.md` documents the fallback (`depth_available: false`). |
| 2 | Review submit | `app/api/studio.py:523-572` — `review_submit` reads `action.get("decision")` expecting `"approved"`/`"rejected"`. | **Bug:** `TurboReview.tsx:159-162` posts `{image_id, action: "approve"|"reject"|"flag"}`. `decision` is never present → every submit is silently skipped (`continue`, line 545) → `processed: 0`. Approve/reject from TurboReview currently does nothing. |
| 3 | Review queue | `app/api/studio.py:481-520` — `review_queue` returns per image only `annotations` (className/confidence/bbox from `human_labels`). No `mask`, no `bbox_3d`. | `TurboReview.tsx:258-270` renders `ann.mask` and `ann.bbox_3d.corners`, but the server never sends them → masks/3D are dead UI today. |
| 4 | Persist field | `app/models/annotation.py:37-40` — Annotation has both `human_labels` and `qa_labels` JSONB; `is_certified` bool at line 60. | QA refinements should write `qa_labels` (semantically separate from annotator `human_labels`), with `AnnotationAction(action_type="refine")` for the audit trail. |
| 5 | Depth estimator | `app/ai/depth_estimator.py` lazy singleton, `DEPTH_MODEL_PATH` env override, `_heuristic_depth` fallback (Phase 11 A1/A2 landed). | Once the ONNX exists at the default path (or `DEPTH_MODEL_PATH`), `depth_available` flips true automatically — no backend code change expected. |

---

## Item 1 — Download the Depth-Anything-V2-Small ONNX

### 1.1. Run the existing script (ops, not code)
- From repo root: `./scripts/download_depth_model.sh`. It is already idempotent and writes `depth_anything_v2_vits.onnx` + `.sha256` into `frontend/public/models/`. If a partial file from the aborted transfer exists, the checksum check handles it (re-download).
- **Do not modify the script unless the download fails.** If the HuggingFace mirror (onnx-community/depth-anything-v2-small) is unreachable, only then: switch `DEPTH_MODEL_URL` to a documented mirror (e.g. the official depth-anything release) and note the size + sha256 in the README.

### 1.2. Verify artifact
- Confirm `shasum -a 256 -c depth_anything_v2_vits.onnx.sha256` passes.
- Smoke-test the estimator end-to-end (no restart tricks): `python -c` or a small script that calls `get_depth_estimator().estimate(...)` on a synthetic image and prints `depth_available` — must be true and must return a real inverse-depth array (not the heuristic path). Log line must NOT show `depth_estimator_heuristic_only`.
- Keep the heuristic fallback intact (it still serves when the artifact is removed or `DEPTH_MODEL_PATH` points nowhere).

### 1.3. Docs
- Update `frontend/public/models/README.md` with the artifact size + sha256 once downloaded; note that live frames will now show depth-grade distance chips (`≈` prefix disappears when `distance_quality === "depth_map"`).

**Acceptance (Item 1):** artifact present + checksum-verified; estimator smoke test returns depth-grade output; heuristic path still works when the model file is renamed away (negative test); README updated.

---

## Item 2 — TurboReview Refine-Save

### 2.1. Fix the submit-shape bug (blocker, no scope debate)
- **Decision:** standardize on the server contract (`decision: "approved"|"rejected"`) and make the client conform — the server already persists `CERTIFIED`/`REJECTED` and the audit trail from it.
- `TurboReview.tsx` `submitBatch` (lines 158-177): map `action` → `decision` (`approve→approved`, `reject→rejected`, `flag→flagged`).
- Add server handling for `"flagged"` as a third decision: set `status` to `AnnotationStatus.PENDING` (or a documented `FLAGGED`-equivalent without a schema change — prefer keeping status `PENDING` and recording the `flag` via `AnnotationAction(action_type="review_flagged")` so no enum/migration is needed).
- Add a regression test proving the fixed contract: `tests/test_studio_review.py` — POST `/studio/sessions/{id}/review-submit` with `{"actions":[{"image_id": X, "decision":"approved"}]}` → `processed:1`, `Annotation.status == CERTIFIED`, `AnnotationAction(action_type="review_approved")` written. Assert the *old* client shape (`action: "approve"`) is rejected or mapped explicitly (decide: map `action` as a compat alias so an old cached client can't silently no-op again — map both keys, prefer `decision`).

### 2.2. review-queue returns the refine targets
- `app/api/studio.py` `review_queue` (481-520): for each image also return, when present:
  - `mask`: normalized polygon from `detected_objects[].mask` (polygon format; omit RLE-only cases or decode via `_polygon_to_mask`-style helper into a polygon when `mask_format === "polygon"` — for RLE-only, fall back to the polygon if stored, else omit),
  - `bbox_3d`: `{ corners: [[x,y],×8], dimensions_m, distance_m, yaw_rad, distance_quality }` (normalized corners),
  - `confidence` and `track_id` from the detection.
- Match objects to images: images are per-`Annotation`; `detected_objects` already holds the per-frame list — take the first (or best-confidence) object per image for refine targets, or return the full list under `detected_objects` and let the client pick. Prefer returning the full list (`detected_objects` passthrough) so QA can refine any object, not just the first.
- Keep response additive — do not change existing `annotations`/`has_human_labels` fields.

### 2.3. Refine editing UI (TurboReview)
- `TurboReview.tsx`: when an image is in an editable state (not yet submitted), render the mask polygon and cuboid with **draggable vertices** (same normalized-coordinate model as the overlay; reuse `orientation.ts`/`drawAnnotations.ts` helpers where applicable):
  - Mask polygon: drag points; add/remove vertices sparingly (keep point cap ≤ 32, mirror the server cap).
  - Cuboid: drag the 8 projected corners independently (crude but honest — QA corrects projection, not true 3D); or "drag to re-project" is out of scope (no 3D editing) — document that vertex correction is a 2D correction of the 2D projection only.
- Store per-image unsaved `refines: { mask?: number[][], bbox_3d?: { corners: number[][] }, objects: [...] }` in component state; clear after submit; a dirty indicator (`unsaved`) shows when refines exist.
- Keyboard flow unchanged (approve/reject/flag via arrows/F); Enter (submitBatch) persists refines alongside decisions.

### 2.4. Persist refines (server)
- Extend `POST /studio/sessions/{session_id}/review-submit`:
  - Accept an optional per-action `refines` object.
  - On any decision (approved/rejected/flagged), if `refines` present: set `annotation.qa_labels = {"refines": [...]}` (merge/replace? — **replace** the `refines` key only, keep other `qa_labels` keys), write `AnnotationAction(action_type="refine", payload={"refines": ...})`.
  - Normalize/validate: each polygon point and corner must be `[0..1]` numbers; arrays bounded (points ≤ 32, corners == 8); reject 422 otherwise. Never touch `human_labels`.
- `qa_labels` round-trip: `GET /studio/annotations/{annotation_id}` may optionally expose `qa_labels.refines` so a follow-up review sees prior QA corrections.

### 2.5. i18n + tests
- i18n (en + ny): "Unsaved refine", "Refining N object(s)", "Mask points (32 max)" as needed.
- Tests:
  - `tests/test_studio_review.py` (new): submit-shape regression (2.1), flag handling, refine persistence (mask polygon + corners round-trip normalized), validation rejects bad shapes (points > 32, corners ≠ 8, coords outside 0..1), `human_labels` untouched, `AnnotationAction` rows written.
  - Vitest: extract the `action → decision` mapping and refine-state merge into a pure helper (`utils/reviewRefine.ts`) and unit-test it; keep TurboReview component tests minimal.

**Acceptance (Item 2):** TurboReview approve/reject actually flips status (regression-fixed); masks + cuboids render from `review-queue`; vertex drags persist to `qa_labels` on submit with audit actions; all new tests green; old client shape can no longer silently no-op.

---

## Item 3 — Manual Smoke-Test Runbook

### 3.1. Deliverable
- Write `docs/smoke-test-live-pipeline.md` (new file) — a numbered, operator-executable runbook covering the full live path. Structure it exactly around these stages, each with prerequisites, steps, expected result, and a "fail → likely cause" column:

1. **Pre-flight:** `docker compose up -d`; `alembic upgrade head`; confirm `/health`, `/metrics` (WS counters present), and that depth artifact is present (`depth_available` should be true after Item 1) — else expect heuristic `≈` chips.
2. **Live annotate:** `/live-annotate` with front camera → default un-mirrored; toggle mirror → boxes stay aligned, WYSIWYG save; enable `VITE_ENABLE_ORIENTATION_DEBUG` probe → markers coincide at 0px; screen share never mirrored.
3. **Masks + 3D:** object_detection model → mask polygons + cuboids render; with depth model, distance chips have no `≈`; with heuristic, `≈` shows.
4. **Save & review:** Save Frame with `dataset_id` → frame appears in `review_queue?scope=live` (Phase 11 C); TurboReview live filter → approve (decision) → status CERTIFIED + audit log; reject path; **verify the fix from Item 2 (submit actually processes; `processed:1`)**.
5. **Refine:** in TurboReview drag a mask vertex + a cuboid corner → submit → `qa_labels.refines` persisted (check via API); `human_labels` unchanged.
6. **Export:** build/export the dataset → COCO includes `segmentation` + attributes; YOLO-Seg `.txt` companion appears when masks exist; VOC has `<segmentation>` + metadata; preview shows orientation badge + distance chips.
7. **Dedup:** capture scene normally → save; toggle mirror → save same scene → dedup clusters them (`orientation_mixed: true`); a different scene stays separate.
8. **Offline/QA of offline:** with WS down (stop app or airplane mode), capture at adaptive rate → on-device seg (`engine: ondevice`) → frames queue in `liveFrameQueue`; restart WS → reconcile via checksum → no duplicate frames after reconnect; retry backoff visible in sync UI.

### 3.2. Rules
- The runbook is instructions-only (no code), written for an OPERATOR/QA audience with the exact commands, URL paths, and expected JSON where useful.
- Cross-reference the phase docs (`PHASE9/10/11` prompts) instead of duplicating design rationale.
- Do NOT run the stack during this phase unless asked; this is a written artifact.

**Acceptance (Item 3):** runbook exists at `docs/smoke-test-live-pipeline.md`, covers all 8 stages, includes the Item 2 regression check, and each stage states expected output + failure triage.

---

## Technical Constraints

- **No schema migrations** (JSONB additive only; `flagged` handled via existing `PENDING` + action record, no enum change).
- **i18n:** all new strings in both `en.json` and `ny.json`.
- **Honesty invariants:** QA vertex edits are 2D corrections of a 2D projection (document in UI copy); on-device seg carries no depth; heuristic depth always labeled `≈`.
- **Backend pattern parity:** new endpoint/validation logic uses existing `app/api/studio.py` conventions and `AnnotationAction` audit records.

## File Touch-Points

| Item | Backend | Frontend | Docs/Assets |
|------|---------|----------|-------------|
| 1 | (none expected) | — | `frontend/public/models/depth_anything_v2_vits.onnx` (+.sha256), `frontend/public/models/README.md` |
| 2 | `app/api/studio.py` (review_submit, review_queue), `app/api/review.py` (flag mapping if needed) | `TurboReview/TurboReview.tsx`, new `utils/reviewRefine.ts`, i18n `en.json`/`ny.json` | — |
| 3 | — | — | `docs/smoke-test-live-pipeline.md` |

## Definition of Done

- Depth artifact downloaded + checksum-verified; estimator returns depth-grade output; heuristic negative test passes; README updated.
- Item 2 blocker fixed (submit processes, regression-tested); refines render, edit, persist to `qa_labels` with audit actions; all new pytest + Vitest green; typecheck/build green.
- Smoke-test runbook written and covering all 8 stages.
- No schema migration, no new runtime deps, i18n complete.

## Out of Scope

- True 3D vertex editing (cuboid corners are 2D-correction only); yaw re-estimation from QA edits.
- Running the smoke test itself (runbook only); Docker/CI automation of the runbook.
- Anything beyond the three listed items — Phase 11 stands complete otherwise.
