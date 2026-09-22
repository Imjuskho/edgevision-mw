# UX Audit Findings — EdgeVision Studio

**Audit date:** 2026-08-12  
**Scope:** Track A UX audit — 19 screens + app shell (`edgevision-mw/frontend/src`)  
**Method:** Source review across nine lenses; findings only, no fixes  
**Severity:** High / Medium / Low (aligned with `edgevision-mw/AUDIT_FINDINGS.md` tier model, UX-only)

---

## Audit lenses

1. **Navigation & information architecture** — wayfinding, deep links, duplicate entry points, context switching  
2. **Discoverability & affordances** — shortcuts, help, hidden features, actionable empty states  
3. **Error handling & feedback** — silent failures, toasts, loading/disabled states, destructive actions  
4. **Empty & loading states** — skeletons, guidance, distinguish empty vs error  
5. **Accessibility** — keyboard, focus, ARIA, labels, contrast, native dialogs  
6. **Responsiveness & low-bandwidth tolerance** — mobile layout, offline, polling, heavy assets  
7. **Consistency & design system adherence** — tokens, icons, inline styles, component reuse  
8. **Internationalization** — `en` / `ny` coverage, language switcher, hardcoded copy  
9. **Role/permission clarity** — ADMIN vs QA, gated nav, permission feedback  

---

## Summary

| Severity | Count |
|----------|-------|
| **High** | 15 |
| **Medium** | 34 |
| **Low** | 24 |
| **Total** | **73** |

### What's working well

- URL routing with dataset-scoped paths, legacy redirects, and route-level `SessionGate` for annotation deep links  
- Lazy-loaded routes with `Suspense` + skeleton fallback; `ErrorBoundary` around main content  
- `UnsavedWorkContext` + confirm-before-leave on session views; Dexie queue keyed by `sessionId` (flush on success only)  
- `DatasetBrowser`: search, type filters, skeleton loading, empty state, pagination  
- `HealthDashboard`: i18n-backed metrics, charts, refresh  
- `LabelSelector`: keyboard support (L, arrows, Enter, Escape)  
- `UploadPage`: multi-mode capture (files, webcam, screen, URL) with drag-and-drop  
- Sidebar offline badge and pending sync count with manual sync trigger  

---

## High severity

### H1. Annotation saves bypass the offline sync queue — no fallback when network drops

**Lens:** Responsiveness & low-bandwidth tolerance  
**Screens:** `annotate`, `agriAnnotate`, `segment`  
**Files:** `pages/AnnotationPage.tsx`, `pages/SegmentPage.tsx`, `hooks/useOfflineSync.ts`

Annotate and segment call `studioApi.saveAnnotation` / `studioApi.saveRoadAnnotations` directly. The Dexie sync queue (`queueAction`, `annotationDrafts`) exists but is never written by the primary save path. Network loss at Save time fails with no local queue fallback.

**Impact:** Transient connectivity loss during labeling is a data-loss event unless the user manually retries after reconnecting. Sidebar sync UI reflects infrastructure the labeling workflow does not use.

*Pre-flagged from Phase 0 routing migration.*

---

### H2. Mobile navigation is absent — sidebar hidden with no replacement

**Lens:** Responsiveness  
**Screens:** App shell (all post-login views)  
**Files:** `App.tsx`, `styles/studio-redesign.css` (L1704–1705), `styles/studio-phase4.css` (L66–81)

At ≤768px the sidebar is `display: none`. CSS defines `.mobile-menu-btn` but no hamburger or alternate nav is wired in `App.tsx`.

**Impact:** Mobile/tablet users lose all navigation after login; most screens are unreachable.

---

### H3. Segment page uses undefined layout class — three-pane layout broken

**Lens:** Consistency / Responsiveness  
**Screens:** `segment`  
**Files:** `pages/SegmentPage.tsx` (L256), `styles/studio-redesign.css` (L696–735)

Root wrapper uses `segment-page-layout`, which has **no CSS definition**. Intended flex layout is on `.segment-layout` (parent wrapper in `AppRoutes` only). SegmentPage renders its own sidebar + canvas + panel inside the wrong class.

**Impact:** Road segmentation UI stacks or overlaps incorrectly on typical viewports.

---

### H4. Health and Dedup cross-navigation callbacks never wired

**Lens:** Navigation & IA  
**Screens:** `health`, `dedup`  
**Files:** `components/HealthDashboard/HealthDashboard.tsx`, `components/DedupPanel/DedupPanel.tsx`, `routes/AppRoutes.tsx`

`onNavigate` props for Health quick actions (“Run Deduplication”, “Build Export”) and Dedup post-submit redirect to Health are defined on components but **not passed** from `AppRoutes`.

**Impact:** In-app workflow buttons on Health and Dedup do nothing when clicked.

---

### H5. Annotate toolbar desyncs from ImageSidebar index

**Lens:** Discoverability / IA  
**Screens:** `annotate`, `agriAnnotate`  
**Files:** `pages/AnnotationPage.tsx`, `routes/AppRoutes.tsx`

Toolbar prev/next updates local `currentIndex` only; never calls parent `setImageIndex`. `ImageSidebar` reads parent `imageIndex` from `App.tsx`.

**Impact:** Sidebar highlight desyncs from canvas position after toolbar navigation; users lose track of which image they are annotating.

---

### H6. QA Review shows metadata only — no image preview

**Lens:** Accessibility / core workflow  
**Screens:** `review`  
**Files:** `pages/ReviewPage.tsx`

Review detail shows label, bbox coordinates, and confidence but **no image preview** or annotation overlay on the image.

**Impact:** Visual QA is effectively blocked; reviewers cannot verify labels against pixels.

---

### H7. Chichewa locale loaded but no language switcher; most UI hardcoded English

**Lens:** Internationalization  
**Screens:** App shell, most pages  
**Files:** `i18n/index.ts`, `App.tsx`, `pages/DatasetBrowser.tsx`, `pages/TrainingPage.tsx`, etc.

`ny.json` exists and i18n is initialized with `lng: 'en'` hardcoded. No UI to switch language. Most shell and page copy is hardcoded English outside `t()`.

**Impact:** Chichewa-speaking field annotators see English-only UI despite bilingual locale infrastructure.

---

### H8. Fleet destructive commands fire without confirmation

**Lens:** Error handling / Role clarity  
**Screens:** `fleet` (Nodes)  
**Files:** `pages/NodeManagementPage.tsx`

`REBOOT`, `UPDATE_FIRMWARE`, `EMERGENCY_UPLOAD`, and `THROTTLE` execute on single click with no confirm dialog.

**Impact:** Accidental clicks can reboot edge nodes or trigger emergency uploads with no undo.

---

### H9. Global dataset selector capped at first page of results

**Lens:** Navigation & IA  
**Screens:** App shell  
**Files:** `App.tsx`

Sidebar `<select>` lists datasets from initial page-1 fetch (20 items). `loadMoreDatasets` is only triggered from the Datasets browser page, not the selector.

**Impact:** Users with >20 datasets cannot select missing datasets from the global selector without visiting Datasets and loading more first.

---

### H10. Queue claim/submit has no error handling or feedback

**Lens:** Error handling  
**Screens:** `queue`  
**Files:** `pages/QueuePage.tsx`

`claimJob` and `submitJob` have no error handling, loading state, or success feedback; API failures are silent.

**Impact:** Users believe a job was claimed or submitted when the API may have failed.

---

### H11. Dedup CLIP embedding step blocks UI sequentially on slow links

**Lens:** Low-bandwidth / Performance  
**Screens:** `dedup`  
**Files:** `components/DedupPanel/DedupPanel.tsx`

“Compute CLIP Embeddings” sequentially POSTs per image (up to 200) with no cancel, accurate batch progress, or rate-limit feedback.

**Impact:** On slow rural links the UI appears frozen for long periods; users may navigate away mid-operation.

---

### H12. Icon-only controls lack accessible names

**Lens:** Accessibility  
**Screens:** App shell, `annotate`, `segment`, `review`  
**Files:** `App.tsx`, `pages/AnnotationPage.tsx`, `pages/SegmentPage.tsx`, `pages/ReviewPage.tsx`

Prev/next, logout, and review approve/reject use icon-only or symbol buttons (SVG, ✓/✗) without `aria-label`.

**Impact:** Screen reader users cannot identify control purpose.

---

### H13. Export build failures are silent

**Lens:** Error handling / Feedback  
**Screens:** `export`  
**Files:** `components/ExportPreview/ExportPreview.tsx`

Export build poll on `FAILED` or network error clears interval and resets `isBuilding` but **does not surface an error message**.

**Impact:** Users think export may still be processing or succeeded when it failed.

---

### H14. Review job actions use native prompt and lack confirmations

**Lens:** Navigation & IA / Error handling  
**Screens:** `review`  
**Files:** `pages/ReviewPage.tsx`

Job-level reject uses native `prompt()`. Certify/reject-all have no secondary confirmation beyond a single click.

**Impact:** Easy to accidentally reject or certify entire jobs; `prompt()` is poor UX and inconsistent across platforms.

---

### H15. Segment page has no loading/empty state for image list

**Lens:** Empty & loading states  
**Screens:** `segment`  
**Files:** `pages/SegmentPage.tsx`

`listImages` has no loading or error UI. Empty `images` yields blank canvas with `0 / 0` counter and no guidance.

**Impact:** Users opening segment on empty datasets see a broken workspace with no explanation.

---

## Medium severity

| ID | Lens | Screen(s) | Files | Finding | Impact |
|----|------|-----------|-------|---------|--------|
| M1 | Navigation | App shell | `App.tsx`, `paths.ts` | Session nav without selected dataset silently redirects to `/datasets` with no toast | Users don't understand why navigation "didn't work" |
| M2 | Navigation | App shell | `AppRoutes.tsx` | Catch-all `*` redirects to `/` with no 404 message | Broken bookmarks lose context |
| M3 | Discoverability | App shell | `App.tsx`, `KeyboardShortcuts.tsx` | Global shortcuts implemented but `ShortcutHint` never rendered; no help overlay | Power features hidden |
| M4 | Discoverability | App shell | `App.tsx` | Admin shortcuts 4/5 silently no-op for non-admins | No feedback that role is required |
| M5 | Role clarity | App shell, admin, review | `AdminRoute.tsx`, `App.tsx` | ADMIN and QA share identical access; topbar shows name only, not role | Permission model unclear |
| M6 | i18n | home | `App.tsx` | Dashboard hero, quick actions, health labels hardcoded English | Dashboard excluded from bilingual support |
| M7 | i18n | datasets | `DatasetBrowser.tsx` | All headings, filters, empty state hardcoded English | Dataset screen English-only |
| M8 | i18n | annotate, agriAnnotate | `LabelSelector.tsx`, `AnnotationCanvas.tsx` | Agri labels use `.en` display names only | Chichewa labels never appear in picker |
| M9 | i18n | roadAnalysis, agriAnalysis, roadTaxonomy | respective pages | Titles, loading/error copy hardcoded; locale keys exist but unused | Analysis/taxonomy English-only |
| M10 | i18n | dedup, segment | `DedupPanel.tsx`, `RoadSegPanel.tsx` | Hardcoded English despite `dedup.*` / `roadSegmentation.*` keys | Dedup/seg panel English-only |
| M11 | i18n | training | `TrainingPage.tsx` | Entire page hardcoded English; no locale keys | Training English-only |
| M12 | i18n | fleet | `NodeManagementPage.tsx` | All labels, empty states, commands hardcoded English | Fleet English-only |
| M13 | Consistency | agriAnnotate | `AnnotationPage.tsx` | Identical layout to road annotate; only nav label differs | Wrong taxonomy context easy to miss |
| M14 | Navigation | home, datasets | `App.tsx`, `AppRoutes.tsx` | Home (no dataset) and `/datasets` both render `DatasetBrowser` with different props | Duplicate entry points, subtle behavioral differences |
| M15 | Error handling | home | `App.tsx` | Health fetch swallows errors; card never appears on failure | Can't distinguish loading vs unavailable vs error |
| M16 | Empty/loading | annotate | `ImageSidebar.tsx` | No loading skeleton or error state on `listImages` failure | Empty sidebar with no explanation |
| M17 | Empty/loading | roadTaxonomy | `RoadTaxonomyPage.tsx` | API failure silently caught; indistinguishable from empty taxonomy | Can't tell fetch failed |
| M18 | Error handling | training | `TrainingPage.tsx` | Job/model list fetch failures silently ignored | Empty history may mean error or no jobs |
| M19 | Error handling | fleet | `NodeManagementPage.tsx` | `loadNodes` failure sets empty array, no error message | Appears as "no nodes" when API is down |
| M20 | Error handling | review | `ReviewPage.tsx` | Per-annotation approve/reject: no loading, error feedback, or undo | Action success unknown |
| M21 | Feedback | liveAnnotate | `LiveAnnotatePage.tsx` | Save frame success has no toast (comment only) | Users don't know if frame saved |
| M22 | Feedback | dedup | `DedupPanel.tsx` | Analysis progress bar fixed at 50% during polling | Misleading progress |
| M23 | Discoverability | admin | `AdminAssignPage.tsx` | Annotators entered as raw comma-separated UUIDs | High assignment error rate |
| M24 | Discoverability | upload | `UploadPage.tsx` | Route-scoped `datasetId` pre-filled but editable | Accidental upload to wrong dataset |
| M25 | Responsiveness | segment | `studio-redesign.css` | `.road-seg-panel` fixed 300px; no mobile collapse | Panel crowds canvas on narrow screens |
| M26 | Responsiveness | fleet | `studio-redesign.css` | `.fleet-layout` fixed 3-column grid, no breakpoints | Horizontal overflow on tablets |
| M27 | Responsiveness | roadAnalysis, agriAnalysis | `studio-redesign.css` | Stat cards 4-column; partial mobile collapse | Cramped cards on small screens |
| M28 | Responsiveness | App shell | `studio-redesign.css` | At ≤1024px sidebar icon-only and **hides dataset selector** | Tablet users lose sidebar dataset switching |
| M29 | Accessibility | login | `LoginPage.tsx` | Labels not associated with inputs via `htmlFor`/`id` | Screen reader field association weak |
| M30 | Accessibility | export, dedup, training | multiple | Range sliders lack `aria-valuenow` / descriptive labels | Incomplete slider state for AT |
| M31 | Accessibility | Toast | `Toast.tsx` | No `role="status"` or `aria-live` region | Toasts may not be announced |
| M32 | Consistency | App shell | `App.tsx` | Road Analysis and Health share identical nav SVG icons | Harder visual scanning |
| M33 | Consistency | multiple | various pages | Mix of `.btn` / `.page-shell` and large inline `style={{}}` blocks | Uneven responsive behavior |
| M34 | Low-bandwidth | annotate, liveAnnotate | `useAIAssist.ts` | ONNX model download status only in button text | Easy-to-miss on slow first AI use |

---

## Low severity

| ID | Lens | Screen(s) | Finding |
|----|------|-----------|---------|
| L1 | Navigation | login | Post-login uses `window.location.href = "/"` full reload instead of SPA navigate |
| L2 | Discoverability | login | No password visibility toggle or strength hints on registration |
| L3 | Role clarity | login | Self-service registration with no explanation of default role |
| L4 | Consistency | home | Health stat grid inline 4-column without responsive override |
| L5 | Empty/loading | annotate | Empty state text-only; no link to Upload |
| L6 | Discoverability | annotate | `modelUsed` indicator is small secondary text |
| L7 | Consistency | agriTaxonomy | Version hardcoded `v1.0`; road loads version from API |
| L8 | Navigation | taxonomies | Taxonomy pages global; related analysis pages dataset-scoped |
| L9 | Error handling | SessionGate | Session creation error copy English-only |
| L10 | Accessibility | UnsavedWorkContext | Leave confirm uses native `window.confirm`, English-only |
| L11 | Accessibility | dedup | Duplicate thumbnails use `alt=""` |
| L12 | Consistency | fleet | Emoji category icons vs SVG elsewhere |
| L13 | i18n | queue | `t("queue.empty")` fallback; locale defines `queue.noJobs` — key mismatch |
| L14 | Consistency | review | All queue items show hardcoded `SUBMITTED` badge |
| L15 | Discoverability | export | Test split slider visible but `disabled` — looks adjustable |
| L16 | Low-bandwidth | health | Auto-refreshes every 5 min regardless of tab visibility |
| L17 | Low-bandwidth | fleet | Polls every 15s with no backoff when tab hidden |
| L18 | Consistency | training | `hasRunning` disables new training globally, not per dataset |
| L19 | Accessibility | ErrorBoundary | Recovery UI hardcoded English |
| L20 | Discoverability | App shell | Pending sync count in tiny tertiary text |
| L21 | i18n | upload | Tab labels hardcoded; page title uses `t()` |
| L22 | Accessibility | datasets | Sort `<select>` has no visible label |
| L23 | Discoverability | home | Quick actions omit Agri Annotate, Segment, Dedup, Live Annotate |
| L24 | Discoverability | annotate | Label picker "L" shortcut undocumented in UI |

---

## Screen coverage index

| # | Screen | High | Medium | Low |
|---|--------|------|--------|-----|
| 1 | LoginPage | H7 | M29 | L1–L3 |
| 2 | home/Dashboard | H9 | M1, M6, M14–M15 | L4–L5, L23 |
| 3–4 | annotate / agriAnnotate | H1, H5 | M8, M13, M16, M33–M34 | L5–L6, L24 |
| 5 | segment | H3, H15 | M10, M25, M33 | — |
| 6 | datasets | H7 | M7 | L22 |
| 7 | upload | H7 | M24 | L21 |
| 8 | queue | H10 | — | L13–L14 |
| 9 | admin/Assign | H7 | M5, M23 | — |
| 10 | review | H6, H12, H14 | M5, M20 | L14 |
| 11 | dedup | H4, H11 | M10, M22 | L11 |
| 12 | roadAnalysis | H7 | M9, M27 | — |
| 13 | agriAnalysis | H7 | M9, M27 | — |
| 14 | health | H4 | M15–M16 | L16 |
| 15 | fleet/Nodes | H8 | M12, M19, M26 | L12, L17 |
| 16 | liveAnnotate | H7 | M21, M34 | — |
| 17 | roadTaxonomy | H7 | M9, M17 | L8 |
| 18 | agriTaxonomy | H7 | M8 | L7–L8 |
| 19 | training | H7 | M11, M18 | L18 |
| 20 | export | H13 | M30–M31 | L15 |
| — | App shell | H2, H7, H9, H12 | M1–M5, M28, M32–M33 | L20 |

---

## Recommended Phase 2+ prioritization (informational — not in scope)

Findings-only audit; no fixes applied. Suggested fix waves for planning:

1. **Wave A (workflow blockers):** H4, H5, H6, H3, H4 (nav callbacks), H1 (offline saves)  
2. **Wave B (field deployment):** H2, H7, H8, H9, M28, M25–M27  
3. **Wave C (i18n pass):** H7, M6–M12, M8  
4. **Wave D (polish):** Medium/Low accessibility, consistency, discoverability items  

---

## Phase 2 — Wave A complete (2026-08-12)

Implemented workflow-blocker fixes from `AUDIT_UX.md`:

| Finding | Fix |
|---------|-----|
| **H1** | **Partial** — `useResilientSave` queues annotate/agri/segment on network-class failure; see resolution matrix |
| **H3** | Segment root uses `.segment-layout`; removed duplicate wrapper |
| **H4** | Health/Dedup `onNavigate` wired in `AppRoutes` with dataset-scoped paths |
| **H5** | `AnnotationPage` toolbar syncs index via `onNavigate` prop |
| **H6** | `ReviewImagePreview` component with bbox overlays on review detail |
| **H15** | Segment loading/empty states |
| **H2** | Mobile hamburger + slide-out sidebar drawer |
| **H8** | Fleet command confirm dialog |
| **H9** | Sidebar dataset selector auto-paginates all datasets |
| **H13** | Export build failure surfaces error message |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

**Next:** Wave D polish (M3 keyboard help overlay, remaining Low items, broader i18n string pass).

---

## Phase 2 — Wave B/C complete (2026-08-12)

Field-deployment and i18n/accessibility fixes:

| Finding | Fix |
|---------|-----|
| **H7** | `LanguageSwitcher` in topbar; persists `studio_language`; i18n init reads saved locale |
| **H10** | `QueuePage` — loading/error states, claim/submit toasts, confirm before submit |
| **M1** | Toast when navigating to session view without dataset selected |
| **M8** | `LabelSelector` agri names follow active locale (`en`/`ny`) |
| **M21** | `LiveAnnotatePage` save toasts; **online-only Save guard** when offline (H1 scope gap) |
| **M22** | `DedupPanel` analyze poll progress + CLIP embed loop progress bars |
| **M25** | Segment `.road-seg-panel` stacks below canvas at ≤1024px |
| **M26** | Fleet `.fleet-layout` single column at ≤1024px |
| **M27** | Home/agri stat cards 2-column at ≤1024px |
| **M28** | Topbar dataset selector visible when sidebar hides selector |
| **M31** | Toast container `role="status"` + `aria-live="polite"` |
| **H11/M29** | `aria-label` on annotate prev/next, logout, review approve/reject |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

---

## Phase 2 — Wave D complete (2026-08-12)

Polish, discoverability, and remaining Low/Medium items:

| Finding | Fix |
|---------|-----|
| **M3** | `ShortcutHelpOverlay` — `?` key + topbar button lists all nav shortcuts |
| **H7 (nav)** | Sidebar sections, labels, home dashboard, view titles use i18n keys |
| **M32** | Distinct heart icon for Health vs activity chart for Road Analysis |
| **L1** | Login uses SPA auth state (no full page reload) |
| **L5** | Annotate empty state links to Upload |
| **L9** | `SessionGate` error/loading copy i18n |
| **L10** | `UnsavedWorkContext` confirm messages i18n |
| **L11** | Dedup thumbnails descriptive `alt` text |
| **L16** | Health dashboard skips refresh when tab hidden |
| **L17** | Fleet node polling skips when tab hidden |
| **L19** | `ErrorBoundary` recovery UI i18n |
| **L20** | Pending sync badge more visible in sidebar + topbar |
| **L21** | Upload capture mode tabs i18n |
| **L22** | Dataset sort `<select>` has `aria-label` |
| **L23** | Home quick actions include Agri Annotate, Segment, Dedup, Live Annotate |

**Build:** `npm run typecheck` ✓ · `npm run build` ✓

---

## Phase 2 — Resolution matrix (accurate status, 2026-08-12)

**Track A sign-off:** **Not signed off.** Waves A–D addressed the highest-impact workflow blockers; several High items remain partial/open. Do not treat Phase 2 as “all findings closed.”

### Status legend

| Status | Meaning |
|--------|---------|
| **Done** | Finding addressed for stated scope |
| **Partial** | Mitigation shipped; known gaps remain |
| **Open** | Not addressed |
| **Deferred** | Explicitly out of Track A; tracked separately |

---

### High severity (15)

| ID | Status | What shipped | Remaining gaps |
|----|--------|--------------|----------------|
| **H1** | **Partial** | Session + live frame queues; cross-session flush; **eviction** (50 frames / 100MB, prune resolved >7d) | No draft persistence; non-network 4xx/5xx fail without queue; segment skips `updateRoadResult` when queued |
| **H2** | Done | Mobile hamburger + slide-out sidebar | — |
| **H3** | Done | `.segment-layout`; duplicate wrapper removed | — |
| **H4** | Done | Health/Dedup `onNavigate` wired in `AppRoutes` | — |
| **H5** | Done | Annotate toolbar index sync via `onNavigate` | — |
| **H6** | Done | `ReviewImagePreview` bbox overlays | — |
| **H7** | **Done** | Full i18n on analysis, training, fleet, dedup, datasets, RoadSegPanel; Chichewa for key new strings (ny.json) | Road object label picker still English-only (M8) |
| **H8** | Done | Fleet command confirm dialog | — |
| **H9** | Done | Sidebar dataset selector auto-paginates | — |
| **H10** | Done | Queue claim/submit toasts, loading/error, confirm before submit | — |
| **H11** | **Done (Track B Wave 2)** | CLIP embed uses 3-wide concurrent pool, cancel button, per-image failure count; dedup resolve + poll errors surfaced | Still capped at 200 images (page 1); no background Web Worker |
| **H12** | **Partial** | aria-label on annotate, review, RoadSeg, dedup nav; export/dedup/admin range sliders have aria-valuenow | Legacy inline-styled controls on some pages |
| **H13** | Done | Export build failure message surfaced | — |
| **H14** | **Done (Track B Wave 1)** | `ConfirmDialog` for Certify All + Reject All (textarea reason, required validation); per-annotation approve/reject toasts + loading | — |
| **H15** | Done | Segment loading/empty states | — |

---

### H1 — technical detail (for field stress-testing)

**Approach chosen:** try-first, queue-on-network-failure (`useResilientSave` → Dexie `syncQueue` via `queueAction`). Not draft persistence; not online-only documentation for session labeling.

**`isOfflineError` classifies:** `!navigator.onLine`, `ERR_NETWORK`, `ECONNABORTED`, `ETIMEDOUT`, message containing `"timeout"`, HTTP 503/504.

**Request timeout (2026-08-12 hardening):** `studioApi` axios instance now uses **45s timeout** so slow/hung rural links fail fast enough to reach the queue path instead of hanging indefinitely with no queue write. Does **not** cover “online but unusably slow under 45s” or ambiguous TCP half-open states where the browser still reports online.

**Sync flush on reconnect:**

- `window.addEventListener("online", …)` → `triggerSync()` → **`flushAllPendingSessions()`** (Track B: all sessions with pending/failed rows).
- Also: 30s interval while online + manual Sync button in topbar (both flush all sessions).
- **Remaining gap:** `flushSessionSync` is skipped entirely while offline during dataset switch (by design in `UnsavedWorkContext`). Per-session locks prevent concurrent double-flush.

**Screens:**

| Screen | Offline queue | Notes |
|--------|---------------|-------|
| annotate / agriAnnotate | Yes | `saveBboxAnnotations` |
| segment | Yes | `saveRoadAnnotations`; road-result update deferred when queued |
| liveAnnotate | **Yes (Track B Wave 2)** | Offline frame queue in `liveFrameQueue` (blob + annotations); flush via `flushLiveFrameQueue` on reconnect |

---

### Live Annotate — explicit decision

| Track | Decision |
|-------|----------|
| **Now (b)** | **Online-only guard superseded by Wave 2 queue** — Save queues frames offline; uploads on reconnect. |
| **Later (a)** | **Eviction shipped:** max 50 frames / 100MB; evict resolved >7d, then failed, then oldest. No user-facing eviction toast yet. |

---

### Medium severity (34) — summary

| Status | IDs |
|--------|-----|
| **Done** | M1–M4, M6–M12, M13–M21, M23–M32, M34 (partial → banner); M29 (login) |
| **Partial** | M5 (role badge; ADMIN/QA access identical); M8 (road label picker English); M33 (annotate toolbar CSS; other pages still inline styles) |
| **Open** | — |

---

### Low severity (24) — summary

| Status | IDs |
|--------|-----|
| **Done** | L1–L5, L7–L11, L13–L24 (see Wave D + optional follow-ups sections) |
| **Open / minor** | L6 partially addressed (badge); L12 (fleet emoji icons) unchanged |

**Note on L18:** Relabeled in practice — dataset-scoped training block is a **behavior fix**, not cosmetic polish.

---

### Track A exit criteria (recommended)

**Status: Ready for field QA sign-off** with documented partials (H1 session limits, M5/M8/M33).

1. **H1:** Partial accepted — session + live queues with eviction; document sync guarantees for field testers.
2. **H14:** Done (Track B Wave 1).
3. **H7 / Medium i18n:** Done for field deployment surfaces; M8 road picker Chichewa deferred.

---

*Phase 1 complete. Phase 2 Waves A–D delivered; resolution matrix above is the authoritative closure state.*

