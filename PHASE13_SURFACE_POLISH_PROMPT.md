# EdgeVision-MW — Phase 13 Development Prompt
## Surface Polish: Data Surfaces, QA/Ops Consoles, Standard Bits Completion, Persona Home & Login Trust

**Date:** 12 August 2026
**Context:** Phase 12 built the foundation (OKLCH token system + 3-theme WCAG AA, 33-component `ui/` primitive library, shell rebuild with global search/⌘K/notifications/theme/breadcrumbs/offline pill, TurboReview wired, 813/813 Chichewa parity). This phase is the **surface pass**: finish the data/QA/ops screens, complete the remaining standard bits, deliver the persona-aware home + login trust moment, and enforce design-system hygiene. **Annotation unification (LabelCanvas → primary workspace) is explicitly deferred** to a later phase — out of scope here.

**Design invariants (carried over):** tokens are the single source of truth; every screen ships explicit empty/loading/error states; inline styles → tokens; i18n never regresses below 100% parity; `reduced-motion`, `low-data`, and offline-first behavior stay honored; Phase 9–11 invariants (overlay mirror guard, WYSIWYG capture, no silent RLE/depth) untouched.

---

## Verified Current State (code audit, 12 Aug 2026, post-Phase-12)

| # | Area | Verified fact |
|---|------|---------------|
| 1 | Inline styles | **204 `style={{}}`** remain repo-wide (target ≤20). Worst: `ReviewPage.tsx` 30, `UploadPage.tsx` 16, `LabelSelector.tsx` 16, `AnnotationCanvas.tsx` 12, `AdminAssignPage.tsx` 10, `DedupPanel.tsx` 10. |
| 2 | CSS layers | `studio.css` imports tokens/base/primitives/layout **plus legacy phase3, phase4, redesign, dashboard, pages** — duplicates (`.page-shell`, `.home-hero`, `.annotate-layout`) still live in multiple files. Consolidation incomplete. |
| 3 | DatasetBrowser | Phase 12 already landed: `SearchInput`, status filters (all/READY/BUILDING/DRAFT), delete via shared `Modal`. **Still missing:** create, richer card metadata (health chip, last-activity), "resume" affordance, empty-state CTA. |
| 4 | Fleet | `NodeManagementPage.tsx:18-22` still uses **emoji** category icons (🛣🌾🦁🎬👤); dense table, no status summary strip; telemetry as plain table; command runner inline. |
| 5 | ReviewPage | **30 inline styles**; IAA metrics not yet StatCards; `fastReviewMode` toggle exists (Phase 12). |
| 6 | HealthDashboard | Ring gauges exist; **error + empty states still missing** (only loading). |
| 7 | Onboarding | Still the 3-step static `OnboardingBanner` (annotator-only); not a role-aware tour. |
| 8 | PWA/brand | `favicon.svg` + OG meta landed; **`icon-192.png` (558B) / `icon-512.png` (3.5KB) are still placeholder art**; no maskable icon. |
| 9 | Login | No trust copy (privacy/consent/field context); no brand moment. |
| 10 | Primitive tests | Only `Button.test.tsx` (3 tests) has jest-axe coverage; 32 other primitives untested. |

---

## Workstream A — Data Surfaces (finish SU3)

### A1. DatasetBrowser completion
- **Create dataset:** add a "New dataset" action (top-right + empty-state CTA). Backend: verify whether a create endpoint exists; if not, add a minimal `POST /studio/datasets` (name, source type, optional description) with `pytest` coverage — this is the one permitted backend touch this phase (call it out explicitly in the PR).
- **Card metadata:** health score chip (reuse HealthDashboard tone logic), sample count, last-activity relative time, type badge (existing), resume affordance ("Continue labeling" on the user's `studio_last_dataset`).
- **Empty/error states:** use `EmptyState` (CTA → create) and `ErrorState` (retry) — replace ad-hoc text.
- Move sort/filter/search into a shared `Toolbar` pattern (label + `SearchInput` + `Select` + count).

### A2. UploadPage polish
- Migrate the 16 inline styles to tokens; unify the 4 capture-mode tabs under one tabbed surface with shared dropzone chrome; per-file progress via existing primitives; clearer success/duplicate-skipped messaging; ensure light-theme (bright field) legibility.

### A3. Queue + AdminAssign on shared DataTable
- Replace bespoke list/table markup with `DataTable` (sortable columns, filters: status/priority/overdue, row selection, progress bars, sticky header).
- QueuePage claim action stays in-row; AdminAssign create form moves into a `Modal` (not a separate screen). AdminAssign inline styles (10) → tokens.

**Acceptance (A):** DatasetBrowser supports search/filter/sort/create/delete/resume with full state coverage; UploadPage + Queue + Assign use primitives with ≤4 inline styles each; new dataset endpoint (if added) is pytest-covered; empty/loading/error present on all three surfaces.

---

## Workstream B — QA/Ops Consoles (finish SU4/SU5)

### B1. ReviewPage token migration + StatCards
- Remove all 30 inline styles → tokens/classes; IAA summary (completeness/accuracy/overall) becomes three `StatCard`s; filmstrip + detail stay; certify/reject stays on shared `Modal`; keep `fastReviewMode` toggle (verify it still works after migration).

### B2. HealthDashboard completeness
- Add missing `ErrorState` (retry) and `EmptyState` (no metrics yet); migrate ring gauges to `ui/RingGauge` + StatCard; chart palette from tokens; `lastUpdated` + refresh stays.

### B3. Fleet console (NodeManagementPage)
- **Category icons:** replace emoji (`🛣🌾🦁🎬👤`) with the lucide set + per-category color (ROAD/AGRI/WILDLIFE/DOC/BIOMETRIC) — move to a shared `fleetCategory` mapping util.
- **Status summary strip:** online/offline/degraded counts as StatCards at top; keep the 3-col layout (list | detail | alerts) but restyle with primitives.
- **Detail pane:** telemetry as sparklines (recharts, token palette) instead of a dense table; node commands runner in a `Modal` with results; inline styles → tokens.
- `expertMode` gating behavior unchanged.

**Acceptance (B):** ReviewPage + HealthDashboard + NodeManagementPage render fully on tokens; no emoji remain in the app; fleet shows status strip + sparkline telemetry + modal command runner; all three have explicit empty/error states; fastReview still functional.

---

## Workstream C — Standard Bits Completion (finish ST)

### C1. Role-aware onboarding tour (replaces OnboardingBanner)
- Build a coachmark-style tour (reuse `Modal`/`Popover` + a new `Tour.tsx` primitive: steps, highlight target, next/prev/skip, persisted completion per role).
- Role-specific tracks (4–6 steps each): ANNOTATOR (canvas, shortcuts, save/sync, AI assist), OPERATOR (fleet, upload, export), QA/ADMIN (review, fast review, dedup, export), FIELD_TECH (fleet, datasets).
- Replace `OnboardingBanner` render in `App.tsx`; keep existing `onboardingComplete` settings wiring.

### C2. PWA icons + maskable
- Author real **192/512 + 512-maskable** PNGs from the SVG mark. Add `scripts/generate-icons.mjs` using a **devDependency** (`sharp`) or `sips` on macOS — build-time only, not a runtime dep. Update `manifest.webmanifest` (icons + `purpose` incl. `maskable`, theme colors per theme).

### C3. Inline-style sweep (204 → ≤20)
- Migration order: ReviewPage (30) → UploadPage (16) → LabelSelector (16) → AnnotationCanvas (12) → AdminAssignPage (10) → DedupPanel (10) → ScreenCapture/ProfileMenu/AgriAnalysis/RoadSegPanel/SegmentPage → remainder.
- Rule: no `style={{}}` except genuinely dynamic geometry (e.g. progress widths, canvas coords). Add a lint guard: extend ESLint with a `no-inline-styles` rule or a script check (`scripts/check-inline-styles.mjs`) that fails >20.

### C4. CSS consolidation
- Fold legacy `studio-phase3.css`, `studio-phase4.css`, `studio-redesign.css` into `primitives.css`/`layout.css`/`surfaces.css` (new), deleting duplicate selectors (`.page-shell`, `.home-hero`, `.annotate-layout`, dead `.toast-*`). Keep `dashboard.css`/`pages.css` only if genuinely needed after review.
- Visual regression guard: this is a refactor with **no visual change** — run the existing Vitest suites + manual smoke of the 6 key screens (home, annotate, fleet, review, settings, upload) after each file is folded.

### C5. Primitive test coverage
- Extend jest-axe coverage to all interactive primitives (minimally: Button, IconButton, Modal, Select, Tabs, Switch, Checkbox, DataTable, Tooltip, SearchInput, CommandPalette, Toast, RingGauge). One test file per primitive: render + interaction + axe. Add a `test:a11y` aggregate target that runs the whole `ui/` suite (already exists).

**Acceptance (C):** tour shipped with per-role tracks and persistence; real PWA icons + maskable verified in manifest; inline styles ≤20 (script-enforced); CSS consolidated with zero visual regression and no dead selectors; all listed primitives have jest-axe tests.

---

## Workstream D — Persona Home & Login Trust (finish SU3/SU6)

### D1. Role-aware DashboardHome
- Split home by role (session gate already provides role). Data sources stay within what exists today (queue stats, health, fleet summary, sync stats):
  - **ANNOTATOR:** "Today's work" — assigned queue (progress, overdue), one-click "Start labeling" (last/next dataset), recent saves, pending sync count, streak as a calm progress row (respectful, not gamified).
  - **QA/ADMIN:** ops overview — queue health (pending/overdue), IAA trend, dataset health rings (existing), flagged-class list, recent review actions.
  - **OPERATOR:** fleet status strip (from B3 data), recent ingestion/uploads, export pipeline status.
  - **FIELD_TECH:** fleet health + datasets only.
  - **BUYER:** clean marketplace placeholder (title + "coming soon", per Phase 12 out-of-scope).
- Extract persona logic into pure helpers (`utils/homePersona.ts`) for Vitest. Keep hero minimal; quick-action groups retinted to tokens; no non-functional decoration.

### D2. Login trust moment (LoginPage)
- Brand: restrained signal gradient, product mark, "Malawi field annotation" eyebrow, one-line value statement.
- Trust block: privacy-by-design, consent-ledger compliance, jurisdiction note — 2–3 compact lines, not a wall.
- Form: labels + focus rings (already), password-strength meter restyled to primitives, clear error states, **light-theme-first** legibility (bright field use).
- No backend changes; copy goes through i18n (en + ny).

**Acceptance (D):** home renders the correct persona surface per role (tested via `homePersona` unit tests); all six roles verified manually; Login shows brand + trust + field-legible form; 100% i18n parity maintained after new copy.

---

## Technical Constraints

- **Frontend-only** except the single explicitly-requested DatasetBrowser create endpoint (A1) — if added, it must be a minimal read/write endpoint with pytest coverage and no schema migration.
- **No new runtime deps.** Allowed additions: `sharp` or equivalent as **devDependency only** (icon generation), plus any lucide-react icons already available.
- Every new string in **both** `en.json` and `ny.json` via `scripts/sync-i18n.mjs`; parity must stay at 813/813 (or higher, never lower).
- Keep Phase 9–11 invariants; keep the offline-first/Dexie/45s-save architecture; `reduced-motion` + `low-data` honored.
- Backend suites must stay green; existing Vitest suites stay green.

## File Touch-Points

| Workstream | Frontend | Backend | Assets/Tests |
|-----------|----------|---------|--------------|
| A | `DatasetBrowser.tsx`, `UploadPage.tsx`, `QueuePage.tsx`, `AdminAssignPage.tsx` | `app/api/studio.py` (only if create endpoint added) | `tests/test_studio_datasets.py` (if added); Vitest for browser helpers |
| B | `ReviewPage.tsx`, `HealthDashboard/`, `NodeManagementPage.tsx`, new `fleetCategory` util | — | Vitest |
| C | `App.tsx` (OnboardingBanner swap), new `ui/Tour.tsx`, `manifest.webmanifest`, ESLint/scripts | — | `scripts/generate-icons.mjs`, `scripts/check-inline-styles.mjs`, `public/icons/*`, jest-axe per primitive |
| D | `DashboardHome.tsx`, `LoginPage.tsx`, new `utils/homePersona.ts` | — | Vitest `homePersona` + login copy tests |

## Definition of Done

- A, B, C, D acceptance criteria all pass; `npm run typecheck`, `npm run test -- --run`, `node scripts/check-contrast.mjs`, `npm run build` green.
- Inline styles ≤20 (script-enforced); no emoji-as-icons; no dead CSS; every screen has empty/loading/error; all key primitives jest-axe tested.
- i18n parity ≥813/813; role-aware tour + persona home + login trust live; PWA icons real + maskable.
- Backend suites green; any added endpoint pytest-covered; Phase 9–11 invariants intact.

## Out of Scope

- **Annotation unification** (LabelCanvas → primary workspace) — deferred, next phase.
- Backend redesign, data-model changes, new business features (buyer marketplace screens are a placeholder only).
- Visual-regression screenshot tooling (follow-up phase); backend performance profiling.
- Deep Chichewa *translation quality* review beyond coverage parity.
