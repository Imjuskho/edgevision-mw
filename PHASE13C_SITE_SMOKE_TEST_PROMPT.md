# EdgeVision-MW — Phase 13C Prompt
## Run the Site & Smoke-Test the Phase 13/13B Work

**Date:** 12 August 2026
**Objective:** Actually run the full stack, seed realistic data, and verify — through the live UI and API — every Phase 13/13B deliverable plus the Phase 9–12 invariants that must not regress. Produce a results report; fix nothing beyond trivial blockers (report-only for anything else).

**Verified environment (12 Aug 2026):**
- Docker Compose stack **all healthy/Up**: `edgevision-mw-app-1`, `celery_beat`, `celery_worker`, `minio`, `postgres`, `redis`.
- Backend: `http://localhost:8000` (`/api/v1`), docs at `/docs`.
- Frontend: Vite dev server on **port 3000**, proxies `/api` and `/ws` → `localhost:8000` (`frontend/vite.config.ts`).
- Admin user `admin@edgevision.mw` / `admin123` **exists**.
- Existing harness: `scripts/e2e_smoke.sh` (API + route availability — extends cleanly).
- Python venv at `edgevision-mw/.venv`; `pycocotools` installed.

---

## 1. Bring-Up

1. Confirm services: `docker compose ps` (all healthy). If any down, `docker compose up -d` and wait for health.
2. Start frontend: `cd edgevision-mw/frontend && npm run dev` (or confirm an instance is already on `:3000`). Verify `curl -sf http://localhost:3000` returns HTML.
3. Run the existing harness once as a baseline: `./scripts/e2e_smoke.sh` — record result (expected: mostly OK; note any dataset-scoped SKIPs if no dataset exists yet).

## 2. Static Gates (run first, record)

| Gate | Command | Expected now |
|------|---------|--------------|
| Typecheck | `npm run typecheck` | green |
| Unit/a11y | `npm run test -- --run` | ≥33 pass |
| Contrast | `node scripts/check-contrast.mjs` | all pairs pass AA |
| Inline styles | `node scripts/check-inline-styles.mjs` | **expect FAIL at ~146** (known-deferred; verify it *decreased* from 203, and that B1/A2/A3 files are at 0) |
| Manifest icons | `npm run validate:manifest` | green |
| Build | `npm run build` | green, PWA precache lists new icons |

## 3. Seed Data (role users + a real dataset)

### 3.1 Role users (via `docker compose exec -T app python - <<'PY' ...`)
Create (idempotently) and log: `qa@edgevision.mw` (QA), `operator@edgevision.mw` (OPERATOR), `annotator@edgevision.mw` (ANNOTATOR), `fieldtech@edgevision.mw` (FIELD_TECH) using `app.auth.service.create_user` with a known password (`EdgeVision123!`). Confirm each can `POST /api/v1/auth/login` and `GET /auth/me` returns the right role.

### 3.2 Dataset + images
- Create a dataset via the **new Phase 13B endpoint**: `POST /api/v1/studio/datasets` (admin token) — name `Smoke Test DS`, type `photo`. Capture `dataset_id`.
- Upload 2–3 real images: via the UI UploadPage **or** `scripts/seed_training_data.py` (posts to MinIO) **or** `POST /ingest/batch`. Prefer the UI UploadPage since it is itself under test (A2) — upload via the file tab and confirm the success summary.
- Create an annotation session for the dataset; run **AI auto-label** (or the batch auto-label path) so ReviewPage has certified-able content.

### 3.3 Assignment loop (needed for Review/Queue)
- As admin: `AdminAssignPage` → create an assignment for `annotator@edgevision.mw` on the smoke dataset (priority 2, deadline tomorrow).
- As annotator: `QueuePage` → claim it, open the image, add one bbox with a label, submit.
- Resulting assignment must appear in **`ReviewPage` queue** (status SUBMITTED) and in **TurboReview** (fast mode).

## 4. Feature Walkthrough (verify each; record pass/fail + evidence)

### B1 — ReviewPage (the core of this pass)
| Step | Expected |
|------|----------|
| Open `/review` as QA | Queue is a **DataTable**: sortable columns, sticky header, clickable rows drill to detail |
| Open job detail | IAA metrics render as **3 StatCards** with correct `good/fair/low` tone; filmstrip navigation works; status pills use Badge variants |
| Certify | `Modal` opens, accepts optional reason, transitions to CERTIFIED; certify action idempotent-guarded |
| Reject | Reason required; transitions to REJECTED; audit entry written |
| Fast review toggle | `ReviewPage` exposes "Fast review"; toggling loads **TurboReview** at `/datasets/:datasetId/review/fast` (admin) — same session, mask/3D refine controls present, keyboard palette works, submit returns `processed:1` (Phase 11B regression: real decision, not silent no-op) |
| Load/error | Force an offline request → `ErrorState` + `Skeleton` visible, retry recovers |

### A2 — UploadPage
| Step | Expected |
|------|----------|
| All 4 capture-mode tabs render | File / Webcam / Screen / URL; one shared dropzone |
| File upload | Per-file `ProgressBar`; success summary; **duplicate-skipped** messaging on re-upload of same checksum; error state on an invalid type |
| No inline styles | Verified by script (§2) |

### A3 — Queue + AdminAssign
| Step | Expected |
|------|----------|
| `QueuePage` as annotator | DataTable with status/overdue filters, progress bars, **in-row claim → annotate → submit** flow works end-to-end |
| `AdminAssignPage` as admin | DataTable; create form opens in `Modal`; checkbox/select picker for annotators; created assignment appears in queue; `ErrorState`/`EmptyState` on empty/failed loads |

### C2 — PWA Icons
| Step | Expected |
|------|----------|
| `scripts/generate-icons.mjs` re-run | Regenerates `icon-192.png` (~7KB), `icon-512.png` (~24KB), `icon-512-maskable.png`; sizes valid |
| `manifest.webmanifest` | Separate `any` + `maskable` entries, correct `sizes`/`type`/`purpose`; `theme_color` set |
| Browser install prompt (Chrome devtools → Application → Manifest) | Icons render, no errors; favicon present in tab |

### Regression — Phase 9–12 invariants (must not regress)
| Check | Expected |
|-------|----------|
| Home personas | Login as each role → correct persona panel (Annotator "Today's work" / QA-Admin ops / Operator fleet / Field Tech fleet / Buyer placeholder) |
| Login trust moment | Logged-out `/` shows brand eyebrow, privacy/consent copy, strength meter, light-theme legibility |
| Onboarding tour | First login as new annotator shows role-aware coachmark tour; skippable; persists |
| Theme cycle | Topbar toggle cycles System→Dark→Light→High-contrast; `prefers-color-scheme` respected; no flash on reload |
| Language switcher | `ny` switches most UI text; no missing-key fallbacks on the smoke pages |
| Live annotate (Phase 9–11) | Front camera un-mirrored by default; mirror toggle keeps boxes aligned + WYSIWYG save; 3D cuboids + distance chips render (heuristic `≈` OK if no depth model); overlay root has no CSS transform |
| Global chrome | `⌘K` palette + search, notification bell (local), connection/offline pill with sync + low-data toggle, breadcrumbs on `/datasets/:id/<tool>`, skip-to-content link |

## 5. Browser Automation (optional, scoped)

If the run is to be scripted rather than driven by hand: add **Playwright as a devDependency** and write `scripts/e2e-ui.spec.ts` covering only the §4 B1 + A3 flows (login as 3 roles, certify, claim, upload file tab). Keep it deterministic and idempotent; do **not** convert §4 regression into E2E this pass. If Playwright is not viable in this environment, drive the §4 walkthrough manually and note it in the report.

## 6. Reporting Format

Return a report with:

1. **Environment** — service status, ports, commit/working state.
2. **Static gates table** (§2) with actual results.
3. **Feature table** (§4) — one row per step: `PASS / FAIL / BLOCKED` + one-line evidence (URL, request/response, screenshot).
4. **Defects found** — numbered, each with: repro steps, expected vs actual, severity (blocker/major/minor), and whether you fixed it or left it (prefer leave + describe).
5. **Known non-defects** — inline-style gate fails at 146 (expected, deferred); PWA install prompt unavailable headless if that applies.
6. **Recommendations** — next-pass candidates (CSS consolidation, primitive jest-axe, annotation unification).

## 7. Exit Criteria

- All §4 B1 steps pass, including the Phase 11B `processed:1` regression and Phase 9–11 live-annotate invariants.
- §2 static gates green except the documented inline-style count (which must have decreased).
- Every defect is either fixed (with tests) or reported with repro; no blocker-level defects unaccounted for.
- Report delivered in the §6 format; no unrelated code changes made.
