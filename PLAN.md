# EdgeVision-MW UI/UX Overhaul — Step 0 Discovery

**Purpose:** Document the current frontend architecture, file inventory, screens, and design tokens before any UI changes. This is discovery only — no fixes, no Step 1 UX audit.

**Project:** EdgeVision-MW (control plane + annotation studio)  
**Workspace:** `/Users/mac/EDGE VISION DATA PLATFORMS`  
**Primary frontend path:** `/Users/mac/EDGE VISION DATA PLATFORMS/edgevision-mw/frontend`  
**Discovery date:** 2026-08-12

---

## Step 0 scope note

- **Included:** Stack identification, file extensions, screen/route inventory, design tokens.
- **Not included:** Step 1 UX audit, UI code changes, backend business logic changes.
- **Awaiting user review** before proceeding to Step 1.

Step 1 (UX audit) will rank findings using the same **High / Medium / Low** severity model referenced in `edgevision-mw/AUDIT_FINDINGS.md` (which uses CRITICAL + HIGH + MEDIUM + LOW for backend/logic issues; UX findings will use High/Medium/Low only).

---

## 1. Frontend location & architecture

### Where the UI lives

| Location | Role |
|----------|------|
| `edgevision-mw/frontend/` | **Only production UI** — React SPA (“EdgeVision Studio”) |
| `edgevision-mw/app/` | FastAPI backend — **no Jinja2 templates, no `/static` HTML**, no HTMX |
| Workspace root (`clip_dedup/`, `test_images/`, etc.) | Supporting Python packages / test data — **no UI** |

### Deployment model

- **Dev:** Vite dev server on port **3000** proxies `/api` and `/ws` to FastAPI on **8000** (`vite.config.ts`).
- **Prod:** Frontend builds to `frontend/dist/`; backend does **not** mount StaticFiles in `app/main.py` — SPA is served separately (see `edgevision-mw/README.md`, CI `frontend` job).
- **Hybrid:** None. Single React app; backend is API-only.
- **PWA:** `vite-plugin-pwa` + custom service worker `src/sw.ts` (Workbox precache + runtime caching for ONNX/images/API).

### Package identity

- npm name: `edgevision-studio` v0.2.0  
- Entry: `index.html` → `src/main.tsx` → `src/App.tsx`

---

## 2. Stack summary

| Layer | Technology | Notes |
|-------|------------|-------|
| **Framework** | React 18 + TypeScript | Functional components, strict TS (`tsconfig.json`) |
| **Build** | Vite 5 + `@vitejs/plugin-react` | `tsc -b && vite build`; manual Rollup chunks for ONNX, Fabric, Recharts, i18n |
| **Routing** | **None (URL-based)** | `react-router-dom` is in `package.json` but **unused**. Navigation is **view-state** in `App.tsx` (`useState<View>` + conditional render). No deep links, no browser back/forward per screen. |
| **State management** | React Context + local state | `useAuth` (Context), page-level `useState`, custom hooks. `zustand` in deps but **not used**. |
| **Styling** | Plain CSS (global) | Four layered stylesheets; **no Tailwind, CSS Modules, styled-components, or Bootstrap** |
| **Design system** | Informal “EdgeVision Studio Design System” | CSS variables in `src/styles/studio.css` + layout overrides in phase/redesign files |
| **HTTP** | Axios | `src/services/api.ts` — base `/api/v1`, JWT from `localStorage` |
| **Offline** | Dexie (IndexedDB) | `useOfflineSync.ts` — sync queue for annotation actions |
| **i18n** | i18next + react-i18next | English + Chichewa (`en.json`, `ny.json`) |
| **Canvas / annotation** | Fabric.js 6 | Bbox/polygon drawing (`AnnotationCanvas`, `LabelCanvas`, `FabricPolygonManager`) |
| **Charts** | Recharts | `HealthDashboard` only |
| **Maps** | react-leaflet + leaflet | In `package.json` but **no imports in `src/`** (unused) |
| **ML in browser** | onnxruntime-web | Models in `public/models/`; `ai/onnxManager.ts`, `useAIAssist.ts` |
| **Testing** | Vitest + Testing Library | Configured in `package.json`; **no app test files in `src/`** |
| **Lint/format** | ESLint script in package.json | No project-level `eslint.config` in frontend root (script may be stub) |
| **Component library** | Custom | Shared primitives: `Toast`, `Spinner`, `Skeleton`, `ErrorBoundary`, `KeyboardShortcuts` — no MUI/Chakra/shadcn |

---

## 3. File extensions inventory

Extensions under `edgevision-mw/frontend/` excluding `node_modules/`, `dist/`, `dev-dist/`:

| Extension | Count (approx.) | Purpose |
|-----------|-----------------|--------|
| `.tsx` | 35 | React pages and components |
| `.ts` | 21 | Hooks, services, AI utils, types, SW, i18n bootstrap |
| `.css` | 4 | Global design system (`studio.css`, `studio-phase3.css`, `studio-phase4.css`, `studio-redesign.css`) |
| `.json` | 5 | i18n locales (`en`, `ny`), `package.json`, `package-lock.json`, `tsconfig.json` |
| `.html` | 1 | Vite entry shell (`index.html`) |
| `.onnx` | 5 | In-browser / backend-shared ML models (`public/models/`) |
| `.pt` | 3 | PyTorch source weights (`yolov8*.pt`) — not loaded by browser UI directly |
| `.wasm` | 2 | Bundled ONNX runtime assets (via onnxruntime-web) |
| `.mjs` | 2 | ORT WASM loaders in `public/` |
| `.png` | 2 | PWA icons (`public/icons/`) |
| `.webmanifest` | 1 | PWA manifest (`public/manifest.webmanifest`) |
| `.bak` | 2 | Stale backups (`LiveAnnotatePage.tsx.bak`, `useLiveAnnotation.ts.bak`) |
| `.DS_Store` | 1 | macOS metadata (noise) |

**Not present in frontend source tree:** `.jsx`, `.vue`, `.svelte`, `.scss`, `.sass`, `.less`, `.module.css`, `.svg` (icons are inline SVG in TSX).

---

## 4. Screen / route inventory

### Navigation model

- **Auth gate:** Unauthenticated users see `LoginPage` only (`App.tsx` early return).
- **Primary nav:** Left sidebar in `App.tsx` — `NAV_SECTIONS` + Dashboard button.
- **View switching:** `switchView(view: View)` — **not URL routes**.
- **Dataset context:** Global `<select>` in sidebar; many views require a selected `datasetId`.
- **Session-gated views:** `annotate`, `agriAnnotate`, `segment` call `handleStartSession()` before rendering.
- **Role gating:** `admin` and `review` nav items hidden unless `user.role === "ADMIN" || "QA"`.
- **Keyboard shortcuts:** `1`–`0`, `h`, `d`, `e`, `c`, `Escape` mapped in `useKeyboardShortcuts`.

### Implemented screens (view key → UI)

| View key | Sidebar / title | Component | File |
|----------|-----------------|-----------|------|
| *(auth)* | — | Login / Register | `src/pages/LoginPage.tsx` |
| `home` | Dashboard | Hero, quick actions, dataset health summary; or `DatasetBrowser` when no dataset selected | Inline in `App.tsx` + `DatasetBrowser.tsx` |
| `annotate` | Annotate | Road bbox annotation workspace | `AnnotationPage.tsx` + `ImageSidebar` + `AnnotationCanvas` |
| `agriAnnotate` | Agri Annotate | Same as annotate with `taxonomyContext="agri"` | `AnnotationPage.tsx` |
| `segment` | Road Seg | Road segmentation labeling | `SegmentPage.tsx` + `RoadSegPanel` |
| `datasets` | Datasets | Searchable dataset list | `DatasetBrowser.tsx` |
| `upload` | Upload | Image upload / ingestion UI | `UploadPage.tsx` |
| `queue` | Queue | Annotation job queue | `QueuePage.tsx` |
| `admin` | Assign | Job assignment (admin/QA) | `AdminAssignPage.tsx` |
| `review` | Review | QA review queue + detail | `ReviewPage.tsx` |
| `dedup` | Dedup | Duplicate detection panel | `DedupPanel/DedupPanel.tsx` |
| `roadAnalysis` | Road Analysis | Road condition analysis | `RoadAnalysisPage.tsx` |
| `agriAnalysis` | Agri Analysis | Agriculture analysis | `AgriAnalysisPage.tsx` |
| `health` | Health | Dataset health dashboard + charts | `HealthDashboard/HealthDashboard.tsx` |
| `fleet` | Nodes | Edge node fleet list + detail + commands | `NodeManagementPage.tsx` |
| `liveAnnotate` | Live Annotate | Camera/screen capture + live inference | `LiveAnnotatePage.tsx` + `CameraCapture`, `ScreenCapture`, `AnnotationOverlay` |
| `roadTaxonomy` | Road Taxonomy | Road class reference browser | `RoadTaxonomyPage.tsx` |
| `agriTaxonomy` | Agri Taxonomy | Agri class reference browser | `AgriTaxonomyPage.tsx` |
| `training` | Training | Model training job UI | `TrainingPage.tsx` |
| `export` | Export | Export builder + preview | `ExportPreview/ExportPreview.tsx` |

### Embedded sub-views (not top-level nav)

| Component | Used from | Purpose |
|-----------|-----------|---------|
| `TurboReview` | `LabelCanvas.tsx` | Fast-review mode for a session |
| `LabelCanvas` / `LabelSelector` | Annotation flows | Polygon canvas + taxonomy picker |
| `DedupPanel`, `ExportPreview`, `HealthDashboard` | Also reachable as top-level views | — |

### Backend capabilities **without** dedicated frontend screens

These API domains exist on the backend (`app/main.py` OpenAPI tags) but have **no matching UI screen** today:

| Domain | Backend routers | Frontend gap |
|--------|-----------------|--------------|
| **Consent management** | `compliance_router` | No consent recording/withdrawal UI |
| **Dataset marketplace / catalog** | `catalog_router`, `billing_router` | No buyer marketplace, quotes, or purchase flow |
| **Billing / escrow** | `billing_router` | Export builder exists; no credit balance, payment, or delivery UI |
| **Batch ingestion pipeline** | `ingestion_router` | Upload page only — no batch status/monitoring UI |
| **User / team admin** | `admin_router`, `auth_router` | Login/register only — no user management |
| **Analytics A/B** | `analytics_router` | `experiments/abTestConfig.ts` exists; no visible analytics UI |
| **Model registry** | `model_registry_router` | Training page may touch training; no registry management UI |

### Device fleet / detail

- **Fleet list:** `NodeManagementPage` — master/detail layout (`fleet-list` + `fleet-detail`).
- **Device detail:** Inline panel on node selection (telemetry, alerts, remote commands) — not a separate route.

---

## 5. Design tokens & theming

Design tokens are **CSS custom properties**, defined primarily in `src/styles/studio.css` and extended in `studio-redesign.css`. There is **no formal token file** (no Style Dictionary, no Tailwind config). Values are **partially duplicated** across four CSS files with occasional inline hex fallbacks in TSX.

### Color tokens (`:root` in `studio.css`)

| Token | Value | Usage |
|-------|-------|--------|
| `--bg-root` | `#0f172a` | Page background (slate-900) |
| `--bg-surface` | `#1e293b` | Cards, sidebar, topbar |
| `--bg-elevated` | `#334155` | Hover/elevated surfaces |
| `--bg-input` | `#0f172a` | Form fields |
| `--border` | `#334155` | Default borders |
| `--border-light` | `#475569` | Lighter borders |
| `--text-primary` | `#f1f5f9` | Body text |
| `--text-secondary` | `#94a3b8` | Muted text |
| `--text-muted` | `#64748b` | Tertiary text |
| `--text-tertiary` | *(fallback `#666` in redesign)* | Footer/meta — **not in base `:root`** |
| `--accent-blue` | `#3b82f6` | Primary actions, active nav |
| `--accent-blue-dim` | `#1e3a5f` | Active nav background |
| `--accent-green` | `#22c55e` | Success, online badge, brand icon |
| `--accent-green-dim` | `#065f46` | Success backgrounds |
| `--accent-yellow` | `#fbbf24` | Warnings |
| `--accent-yellow-dim` | `#713f12` | Warning backgrounds |
| `--accent-red` | `#f87171` | Errors, offline |
| `--accent-red-dim` | `#7f1d1d` | Error backgrounds |
| `--accent-purple` | `#818cf8` | Secondary accent |
| `--accent-purple-dim` | `#312e81` | Purple backgrounds |

### Layout & shape tokens

| Token | Value | File |
|-------|-------|------|
| `--sidebar-w` | `220px` | `studio-redesign.css` |
| `--topbar-h` | `48px` | `studio-redesign.css` |
| `--radius-sm` | `6px` | Both base + redesign |
| `--radius-md` | `8px` | `studio.css` |
| `--radius-lg` | `12px` | `studio.css` |
| `--radius-xl` | `16px` | `studio.css` |
| `--radius` | `8px` | `studio-redesign.css` (alias) |
| `--transition` | `150ms ease` | `studio-redesign.css` |

### Typography

| Token | Value |
|-------|-------|
| `--font` | `'Inter', system-ui, -apple-system, sans-serif` |
| `--font-mono` | `'SF Mono', 'Cascadia Code', 'Consolas', monospace` |

**Type scale:** Ad hoc per component (e.g. 11px badges, 13px nav, 14–16px body, 24–28px headings) — **no `--text-sm/md/lg` token scale**.

**Spacing:** Ad hoc padding/margin values in CSS (6px, 8px, 12px, 14px, 16px, 24px, 48px) — **no spacing scale variables**.

### PWA / manifest theme

- `theme_color` / `background_color`: `#0f172a` (`vite.config.ts`, `manifest.webmanifest`)

### Taxonomy / chart colors (hardcoded, not CSS vars)

- Road/agri class colors in `constants/roadTaxonomy.ts`, `constants/agriTaxonomy.ts`, `constants/taxonomy.ts`
- Recharts palette in `HealthDashboard.tsx`: `#60a5fa`, `#34d399`, `#fbbf24`, etc.
- Quick-action cards in `App.tsx` use inline hex (`#4CAF50`, `#3b82f6`, `#eab308`, …)

### Inconsistencies noted (for Step 1)

1. Four CSS files loaded in cascade (`studio.css` in both `main.tsx` and `App.tsx`).
2. Legacy `.studio-nav` / `.nav-tab` styles in `studio.css` coexist with sidebar layout in `studio-redesign.css`.
3. `--text-tertiary` used in redesign but not defined in base tokens.
4. Mixed token vs inline color usage in components and pages.

---

## 6. Key source files (reference)

| Concern | Path |
|---------|------|
| App shell + nav + view router | `frontend/src/App.tsx` |
| Auth | `frontend/src/hooks/useAuth.tsx`, `frontend/src/pages/LoginPage.tsx` |
| API client | `frontend/src/services/api.ts` |
| Types | `frontend/src/types/index.ts` |
| i18n | `frontend/src/i18n/index.ts`, `locales/en.json`, `locales/ny.json` |
| Design system CSS | `frontend/src/styles/studio.css` (+ phase3, phase4, redesign) |
| Build / PWA | `frontend/vite.config.ts`, `frontend/src/sw.ts` |
| Backend audit context | `edgevision-mw/AUDIT_FINDINGS.md` |

---

## 7. Next step

**Step 1 — UX audit:** Not started. Awaiting user review of this discovery document. UX findings will be ranked **High / Medium / Low**, aligned with the severity tiers used in `AUDIT_FINDINGS.md`.

---

## 8. Phase 0 completed (2026-08-12)

Phase 0 cleanup and routing migration. No visual output changes intended.

### Dependencies removed

| Package | Reason |
|---------|--------|
| `zustand` | Listed in Step 0 discovery; zero imports in `src/` |
| `react-leaflet` + `leaflet` + `@types/leaflet` | Zero imports in `src/`; lockfile synced via `npm install` |

**Flag — optional future use:** A **map tab on `/nodes`** would help ops see geographically distributed edge devices across rural Malawi. `NodeManagementPage` today is a master/detail list with status colors only — no lat/lng UI. Recommend **deferring** `react-leaflet` until Phase 4 (responsiveness/fleet UX) if a map view is approved; avoids ~40KB+ gzip and tile-fetch bandwidth on slow links until needed.

### Files deleted / gitignore

- Removed stale backups: `LiveAnnotatePage.tsx.bak`, `useLiveAnnotation.ts.bak` (already absent before this pass)
- `.DS_Store` already in workspace root `.gitignore`

### CSS consolidation

Single entry point: `src/styles/studio.css` imports in order:

1. `studio-tokens.css` — **single `:root` token source** (includes `--text-tertiary: #666`, layout tokens, radii, fonts)
2. `studio-phase3.css` — component styles
3. `studio-phase4.css` — component styles
4. `studio-redesign.css` — sidebar layout + page styles

`main.tsx` imports `studio.css` only. Removed duplicate CSS imports from `App.tsx`. Legacy `var(--text-tertiary, #666)` fallbacks remain in redesign CSS (harmless; token is now defined).

### Routing (`react-router-dom`)

Replaced `useState<View>` conditional rendering with URL routes. Keyboard shortcuts (`1`–`0`, `h`, `d`, `e`, `c`, `Escape`) call `navigate()`.

| View key | URL path |
|----------|----------|
| `home` | `/` |
| `annotate` | `/annotate` |
| `agriAnnotate` | `/agri-annotate` |
| `segment` | `/segment` |
| `datasets` | `/datasets` |
| `upload` | `/upload` |
| `queue` | `/queue` |
| `admin` | `/assign` |
| `review` | `/review` |
| `dedup` | `/dedup` |
| `roadAnalysis` | `/road-analysis` |
| `agriAnalysis` | `/agri-analysis` |
| `health` | `/health` |
| `fleet` | `/nodes` |
| `liveAnnotate` | `/live-annotate` |
| `roadTaxonomy` | `/road-taxonomy` |
| `agriTaxonomy` | `/agri-taxonomy` |
| `training` | `/training` |
| `export` | `/export` |

**New files:** `src/routes/paths.ts`, `src/routes/lazyPages.tsx`

**Code-splitting:** Page components lazy-loaded via `React.lazy` + `Suspense` (route-level chunks visible in build output).

**Preserved behavior:** Auth gate, dataset sidebar selector, session creation before annotate/segment, admin/QA role gating on `/assign` and `/review`, offline sync badge, keyboard shortcuts.

**Build:** `npm run typecheck` ✓ · `npm run build` ✓ (PWA SW generation requires non-sandbox environment in this workspace).

### Next: Phase 1

Track A UX audit → append findings to `AUDIT_UX.md` (findings only, no fixes).

---

## 9. Phase 1 completed (2026-08-12)

Track A UX audit across 19 screens + app shell. **73 findings** (15 High, 34 Medium, 24 Low) in `AUDIT_UX.md`.

**Method:** Nine-lens source review (navigation, discoverability, errors, empty/loading, accessibility, responsiveness/offline, consistency, i18n, role clarity). No code changes.

**Top High findings:** offline save path bypasses sync queue (H1); no mobile nav (H2); segment layout broken (H3); Health/Dedup nav callbacks unwired (H4); annotate sidebar desync (H5); review lacks image preview (H6); no language switcher (H7); fleet commands unconfirmed (H8); dataset selector pagination cap (H9).

**Next:** Track B Wave 3 complete — Track A ready for field QA sign-off.

---

## 17. Track B Wave 3 (2026-08-12)

Close-out of open Wave 2 items + a11y/i18n polish:

| Item | Change |
|------|--------|
| **H7** | `RoadSegPanel` full i18n |
| **H1** | Live frame queue eviction (50 entries / 100MB) |
| **M13** | Agri/road mode banners on `AnnotationPage` |
| **M14** | Home without dataset → CTA to `/datasets` (canonical browser) |
| **M24** | Upload dataset field locked when route-scoped |
| **M30** | `aria-valuenow` on dedup, admin, export range sliders |
| **M33** | Annotate toolbar moved to CSS classes |
| **M34** | Prominent AI model loading banner |
| **H12** | Additional aria-labels (RoadSeg, dedup nav) |
| **ny.json** | Chichewa for home browse, annotation banners, live queue |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

**Track A:** Ready for field QA sign-off (see `AUDIT_UX.md` exit criteria).

---

## 16. Track B Wave 2 (2026-08-12)

| Item | Change |
|------|--------|
| **H7 / M9–M12** | i18n: road/agri analysis, training, fleet, dedup, datasets browser |
| **M15–M19** | Error handling: home health, ImageSidebar, taxonomy, training lists, fleet, dedup |
| **M23** | `GET /auth/users?role=ANNOTATOR` + AdminAssign checkbox picker |
| **H1 (a)** | `liveFrameQueue` Dexie v2; offline live save + flush on reconnect |
| **H11** | Concurrent CLIP embed (pool=3), cancel, failure reporting |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

**Remaining:** ~~H7 partial (RoadSegPanel), M13–M14, M24, M30, M33–M34; live queue eviction policy.~~ **Done in Wave 3 (§17).**

---

## 15. Track B Wave 1 (2026-08-12)

Production-readiness follow-ups after Phase 2 Waves A–D:

| Item | Change |
|------|--------|
| **H14** | `ConfirmDialog` on Review certify/reject-all; reject reason textarea (no `prompt()`); per-annotation toasts + busy state |
| **H1 gap** | `flushAllPendingSessions()` on reconnect + manual Sync (cross-session queue flush) |
| **M2** | `NotFoundPage` instead of silent redirect on unknown routes |
| **M4** | Admin shortcuts 4/5 toast when non-admin |
| **M5** | Role badge in topbar (partial — ADMIN/QA access unchanged) |
| **M20** | Per-annotation approve/reject feedback |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

**Next Track B waves:** ~~H7 i18n remainder~~ Done in Wave 2. See §16 for remaining items.

---

## 14. Track A closure status (2026-08-12)

Phase 2 Waves A–D shipped. Authoritative finding status: **`AUDIT_UX.md` → Phase 2 Resolution Matrix**.

- **H1:** Partial (session + live frame queues; eviction policy shipped Wave 3)
- **H14:** Done (Track B Wave 1)
- **H11:** Done (Track B Wave 2)
- **H7:** Done (Track B Wave 3 — RoadSegPanel i18n)

---

## 13. Phase 2 optional follow-ups completed (2026-08-12)

Login UX (L2–L3), annotate model badge (L6), taxonomy API version + analysis links (L7–L8), review/export/training polish (L14–L15, L18), label picker hint (L24).

---

## 12. Phase 2 Wave D completed (2026-08-12)

See `AUDIT_UX.md` Wave D section. Keyboard shortcut overlay, nav/home i18n pass, login SPA flow, empty-state upload link, visibility-aware polling, accessibility polish.

---

## 11. Phase 2 Wave B/C completed (2026-08-12)

See `AUDIT_UX.md` Wave B/C section. Language switcher, queue feedback, responsive tablet fixes, accessibility labels, dedup progress, live-annotate toasts.

---

## 10. Phase 2 Wave A completed (2026-08-12)

See `AUDIT_UX.md` Phase 2 section for full fix list. Workflow blockers H1–H6 addressed; partial Wave B (H2, H8, H9, H13, H15).
