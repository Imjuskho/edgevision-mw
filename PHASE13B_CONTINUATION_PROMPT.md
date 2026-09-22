# EdgeVision-MW — Phase 13B Continuation Prompt
## Focused pass: ReviewPage Token Migration → Data Surfaces DataTable → PWA Icons

**Date:** 12 August 2026
**Context:** Continuation of Phase 13. Workstreams A1/B(partial)/C1/D are done (verified: `POST /studio/datasets`, `Toolbar`, `Tour`, `homePersona`, `fleetCategory`, HealthDashboard + fleet restyle, login trust). This pass closes the three remaining items in priority order. Annotation unification remains out of scope. Inline-style budget: 203 remaining, target ≤20 (enforced by `scripts/check-inline-styles.mjs`).

---

## 1. B1 — ReviewPage token migration (do first)

`src/pages/ReviewPage.tsx` currently carries **30 of the 203 remaining inline styles** — the largest single offender; clearing it is the biggest step toward the C3 sweep target.

- Replace all 30 `style={{}}` with tokens/classes (`text-primary/secondary/muted`, `--border`, spacing scale, `Badge`/`Chip` statuses). Keep genuinely dynamic values only where geometry demands it.
- IAA summary (completeness/accuracy/overall) → three `ui/StatCard`s; tone logic from HealthDashboard's existing scoreTone mapping (≥75 good / ≥45 fair / else low).
- Keep: assignment table → detail drill-in, filmstrip navigation, per-item busy state, certify/reject via shared `Modal` (reason textarea), and the Phase 12 `fastReviewMode` toggle — verify fast review still works after the migration.
- Per-image status pills already use accent vars; standardize via `Badge`.
- **DoD:** `ReviewPage.tsx` ≤ 2 inline styles; IAA StatCards render with correct tones; fast review path re-smoked; no behavior change.

## 2. A2–A3 — Data surfaces on shared primitives (parallel-friendly)

### UploadPage (`src/pages/UploadPage.tsx`, 16 inline styles)
- Migrate the 16 inline styles → tokens/primitives.
- Unify the 4 capture-mode tabs under one tabbed surface (`ui/Tabs` + shared dropzone chrome); per-file progress via `ProgressBar`; success/duplicate-skipped messaging stays accurate; verify light-theme (bright-field) legibility.
- **DoD:** ≤ 2 inline styles; all 4 modes still capture+upload.

### QueuePage (`src/pages/QueuePage.tsx`) + AdminAssignPage (`src/pages/AdminAssignPage.tsx`, 10 inline styles)
- Rebuild both on `ui/DataTable` (sortable columns, filters: status/priority/overdue, row selection, progress bars, sticky header).
- QueuePage: claim action stays in-row; keep `PageShell` accent.
- AdminAssignPage: move the create-assignment form into a `Modal`; migrate its 10 inline styles.
- **DoD:** both tables sortable/filterable; create-in-modal works; ≤ 2 inline styles each; empty/loading/error states present (via `EmptyState`/`Skeleton`/`ErrorState`).

## 3. C2 — PWA icons (quick win, last)

- Add `scripts/generate-icons.mjs` that renders the brand SVG mark (`public/icons/icon.svg`) to **192, 512, and 512-maskable** PNGs. Tooling: **devDependency** `sharp` (build-time only; not a runtime dep) — or `sips` on macOS as a fallback. No new runtime deps.
- Update `public/manifest.webmanifest`: icon entries with correct `sizes`/`type`, `purpose` incl. `"maskable"` for the maskable asset, and per-theme `theme_color`/`background_color` where supported.
- Replace the placeholder `icon-192.png` (558B) / `icon-512.png` (3.5KB).
- **DoD:** real icons render in install prompt + browser chrome; manifest validates (check via `npx pwa-asset-generator`-free JSON review or a `node` script asserting expected sizes/purposes); `npm run build` green.

---

## Sequence & verification

1. B1 → run `npm run typecheck`, `node scripts/check-inline-styles.mjs` (must drop by ≥28), `npm run test -- --run`, fast-review manual smoke.
2. A2–A3 (parallel) → same checks; verify upload modes + queue claim + create-assignment modal manually.
3. C2 → `node scripts/generate-icons.mjs`, build, confirm manifest entries.

**Final gate:** inline styles ≤ 20 (script green); `typecheck`, Vitest (33+), `build`, `check:contrast` all green; i18n parity maintained at 813/813 via `sync-i18n.mjs`; backend pytest untouched and green; Phase 9–11 invariants intact. Out of scope: ReviewPage/fleet re-architecture, annotation unification, CSS consolidation (deferred to a later pass), remaining primitive jest-axe coverage (also deferred).
