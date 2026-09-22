# EdgeVision-MW — Phase 12 Development Prompt
## UI/UX Overhaul — Design System, Product Surface, Interaction Language, and the Standard Bits Every Serious Platform Has

**Date:** 12 August 2026
**Context:** EdgeVision-MW is a production control plane for a solar-powered edge-vision platform serving rural Malawi — it is simultaneously (a) a **data annotation studio** (bbox, polygon, live camera, 3D cuboids, AI assist), (b) a **fleet & QA operations console** (nodes, telemetry, assignment, IAA review, training, dedup, export), and (c) a **trust-based data marketplace** (consent ledgers, licensing, Malawi Kwacha pricing). It is used on laptops and phones over **unreliable, low-bandwidth rural links**, in bright field light and dark rooms, by six roles. Today it is functionally rich but visually and behaviorally inconsistent: hand-rolled CSS across seven overlapping files, ~205 inline styles, no shared primitives, dead screens (LabelCanvas/TurboReview unwired), no favicon, placeholder PWA icons, 222 untranslated Chichewa keys, and none of the "standard bits" a serious platform ships.

**Goal of this phase:** transform EdgeVision Studio into a **world-class precision tool** — a coherent design system, a consistent component library, a role-aware product surface, a deliberate motion/interaction language, complete i18n and accessibility, and the standard platform affordances (global search, command palette, notifications, breadcrumbs, onboarding, empty/loading/error states, offline-first polish). This is a **frontend-only** phase; no backend/API behavior changes except where a screen needs a small read endpoint (called out explicitly).

---

## 1. Design Philosophy & Brand Thesis

**Thesis — "Precision under harsh light."** EdgeVision is not a consumer app and must not look like one. It is an **instrument** for people doing careful, high-throughput work that pays real wages and feeds real models. The visual language is: dark-first precision (restraint, dense-but-clear information, sharp but humane), with **color used sparingly and semantically** (status, class, workflow), and a single **signal gradient** (green→blue→purple, already the brand) reserved for brand moments, active navigation, and trust signals — never sprayed across controls.

Non-negotiables:
- **Respect the annotator.** They are professionals doing precision work; treat them with the ergonomics of Encord/CVAT-class tools, not consumer gamification. Every microinteraction should reduce friction, not add delight-for-delight's-sake.
- **Trust is a feature.** Consent, audit trails, licensing, and money are core to this product. Trust moments (login, export, consent, payment, destructive actions) get deliberate, calm, high-contrast treatment — never decorative clutter.
- **Offline-first dignity.** The app must behave beautifully at 200 kbps and offline: skeletons not spinners, cached assets, no layout jank, explicit sync state. This is a differentiator, not an afterthought.
- **Contrast is a field requirement.** The existing `high-contrast` theme exists for bright-field outdoor use — the system must guarantee WCAG AA (4.5:1 text) in **all three themes**, and the `light` theme must be genuinely usable at noon in Lilongwe, not a second-class citizen.

**References to study (do not copy wholesale — extract the discipline):**
- **Linear / Vercel (Geist) / Raycast / Superhuman** — dark-first precision, restraint, near-black surfaces, one sparse accent, tight type, swift micro-interactions (active scale ≈0.97, 150ms), dense tool-feel.
- **Encord / Labelbox / CVAT / Label Studio / SuperAnnotate / Roboflow** — annotation ergonomics: keyboard-first labeling, palette-driven class selection, pre-label acceptance flow, QA overlay, minimal chrome around the canvas. 2026 buyer expectations for this class: pre-labels + active learning built in, governance (RBAC, audit trails, QA workflows).
- **Stripe / Wise** — trust-heavy commerce: calm surfaces, explicit money states, honest progress.
- **Anti-references (avoid):** consumer-grade gradients everywhere, glassmorphism, emoji-as-icons, decorative illustration, "AI slop" generic dashboards, motion without purpose.

---

## 2. Verified Current State (grounded audit)

### 2.1 Design tokens (`src/styles/studio-tokens.css`, 101 lines)
Tokens exist (dark `:root`, `[data-theme=light]`, `[data-theme=high-contrast]`) but are **a flat list of ~30 hex values**, not a scale: no typographic scale, no spacing scale, no elevation/shadows, no motion tokens, no focus/ring tokens, no iconography size. `--text-tertiary: #666` fails AA on dark surfaces; `--text-muted` is borderline. Section accents (`--section-labeling/data/quality/analysis/live`) and the brand gradient exist and are good raw material.

### 2.2 CSS architecture (7 files, duplicates, dead code)
Import chain via `studio.css`: `studio-tokens` → `studio-phase3` (809) → `studio-phase4` (362) → `studio-redesign` (2281) → `dashboard` (477) → `pages` (940); `studio.css` itself 1062 lines. **Verified duplicates/conflicts:** `.studio-root` (column vs row), `.page-shell`, `.home-hero`, `.annotate-layout`, `.image-sidebar` each defined 2–3× with later wins; `.toast-container`/`.toast` CSS exists but `Toast.tsx` renders inline styles (dead CSS); ~205 `style={{}}` occurrences (worst: ReviewPage 29, Skeleton 18, UploadPage 16, LabelSelector 16, AnnotationCanvas 12); flat class prefixes with no BEM/utility system.

### 2.3 Component inventory (26 files/folders)
Primitives that exist: `Toast` (inline-styled, no undo), `ConfirmDialog`, `ErrorBoundary` (+`RouteFallback`), `Skeleton`/`SkeletonCard`/`SkeletonTable` (inline), `Spinner`/`LoadingOverlay`, `PageShell` (11 accents), `KeyboardShortcuts`, `ShortcutHelpOverlay`, `LanguageSwitcher` (native `<select>`), `LabelSelector` (the only custom input, 16 inline styles). **Missing:** Modal, Drawer, Menu/Dropdown, Tooltip, Tabs, Badge/Chip, Avatar, Breadcrumbs, EmptyState, Pagination, DataTable, Search, Command palette, Notification center, StatCard, FormField, ProgressBar.

### 2.4 IA & shell (`src/App.tsx` L358-525, `studio-redesign.css`)
Sidebar-first (220px) with 6 nav sections × 20 views, dataset-context selector in sidebar, role-gated (ANNOTATOR 8 views, OPERATOR 12, ADMIN/QA 20, feature flags third layer). Topbar (48px): title, mobile dataset select, language, shortcuts, sync count, role/user badges. **Absent from topbar/global:** search, notifications, theme toggle, avatar/profile menu, breadcrumbs. Keyboard shortcuts exist (`1`-`9`,`0`,`h`,`d`,`e`,`c`,`?`,`Esc`). Mobile: ≤1024px rail, ≤768px drawer. `PageShell` max-width 1180px.

### 2.5 Surfaces (17 pages + 8 widgets)
DashboardHome (hero + ring gauges + 4 color-grouped quick actions); DatasetBrowser (cards, sort dropdown, load-more, **no search/filter/create/delete**); AnnotationPage/SegmentPage (Fabric canvases + ImageSidebar, resilient 45s saves); LiveAnnotatePage (camera + overlay + 3D); ReviewPage (IAA table + detail + confirm dialogs, 29 inline styles); NodeManagementPage (dense table, **emoji category icons 🛣🌾🦁🎬👤**); QueuePage/AdminAssignPage (tables); TrainingPage (jobs + form); HealthDashboard (rings + recharts, **missing error/empty states**); DedupPanel/ExportPreview (wizards); Road/Agri analysis + taxonomies (PageShell reports); SettingsPage (theme + flags + audit); LoginPage (login/register + strength meter). **Dead code:** `LabelCanvas/` (583) + `TurboReview/` (627) are not routed — only `FabricPolygonManager` is used.

### 2.6 i18n, PWA, brand
`en.json` 754 keys / `ny.json` 532 keys (~70%, **222 missing**); ~25 hardcoded strings (LabelCanvas "💾 Save", SegmentPage "Loading model...", UploadPage copy, brand `<span>EdgeVision</span>` literal). PWA: manifest exists, icons **558-byte/3.5KB placeholders**, **no favicon**, title "EdgeVision Studio". Theme applied pre-paint from `studio_settings_v2` (good — keep). Feature flags + settings context already solid (dark default, expert mode, compact sidebar, reduced motion).

---

## 3. Design System Foundation (Workstream DS)

### DS1. Token architecture — replace `studio-tokens.css` with a true scale
Rebuild as a layered token file (`:root` + themes), all consumers must migrate off inline literals:
- **Color:** define ramps via OKLCH (hue-stable). Semantic tokens: `bg-root/-surface/-elevated/-overlay/-inset`, `text-primary/secondary/muted/disabled/on-accent`, `border-default/strong/active`, `accent-*` (status + brand), `success/warning/danger/info` with `-emphasis/-surface/-border/-text` per status. **All three themes (dark/light/high-contrast) must pass WCAG AA; adjust values, not just claim them.**
- **Typography scale:** display (36/700/-0.02em), h1 (24/650), h2 (20/600), h3 (16/600), body (14/400), body-sm (13), caption (12), mono (13) for data/code/coordinates. Line-height 1.5 body, 1.3 display. Font: keep `Inter` (covers Chichewa Latin); add a mono fallback stack for data/IDs.
- **Spacing:** 4px base scale `0,4,8,12,16,20,24,32,40,48,64`.
- **Radii:** `4,6,8,12,16` (map existing sm/md/lg/xl → 6/8/12/16).
- **Elevation/shadows:** `--shadow-sm/md/lg/overlay` (subtle, dark-appropriate), plus `--ring` (focus), `--ring-offset`.
- **Motion tokens:** `--dur-fast:120ms`, `--dur-med:180ms`, `--dur-slow:260ms`; `--ease-out` cubic-bezier(0.2,0,0,1), `--ease-spring` for micro-interactions; `--active-scale:0.97`.
- **Iconography:** fixed size scale `16/20/24`; single stroke-based icon set (see OS4).
- Keep `--section-*` accents and `--gradient-brand` (used per §1 restraint rules).

### DS2. Theming
- Keep dark default, light, high-contrast. **Add "System" (auto via `prefers-color-scheme`)**; settings UI becomes a segmented control (System/Dark/Light/High-contrast).
- Theme toggle must be **one click in the topbar** (move out of SettingsPage), persists to `studio_settings_v2` as today.
- High-contrast = true WCAG AAA attempt; keep no-gradient rule.

### DS3. CSS consolidation
- Consolidate the 7 files into a small set by role: `tokens.css` → `base.css` (reset, typography, focus) → `primitives.css` (new component library) → `layout.css` (shell, nav, responsive) → `surfaces.css` (page-specific, slim). Delete dead CSS (`.toast-*` in redesign, duplicate `.page-shell`/`.home-hero`/`.annotate-layout`).
- **Migration rule:** every page touched must remove inline `style={{}}` in favor of tokens/classes; target ≤ 20 remaining inline styles repo-wide by phase end.
- Introduce **CSS custom-property driven variants** (e.g. `--tone` on `.page-shell`/`.card`/`.badge`) instead of duplicating classes per accent.

### DS4. Iconography (replace emoji)
- Replace **all emoji** (fleet categories 🛣🌾🦁🎬👤, statuses, buttons) with a single consistent 16/20/24px **stroke icon set** (self-contained `components/ui/Icon.tsx` rendering inline SVG paths, OR add `lucide-react` — the single permitted new dependency, tree-shakeable). One icon per semantic meaning, no duplicates.
- Node categories get refined glyphs: ROAD/AGRI/WILDLIFE/DOC/BIOMETRIC as dedicated stroke icons with per-category colors (not emoji).

### DS5. Components (Workstream PR — "Primitives")
Build a token-driven, keyboard-accessible, ARIA-correct primitive library in `src/components/ui/`. Each must ship with: variants, sizes, disabled/loading/error states, focus-visible ring, and a Vitest test (render + interaction + a11y via `jest-axe` — add dev dep).

Required set (build every one, no exceptions):
`Button` (primary/secondary/ghost/danger/outline + icon + loading), `IconButton`, `Input`, `Textarea`, `Select` (custom, searchable, keyboard-nav — replace native selects incl. LanguageSwitcher, AuditLogPanel, sidebar dataset picker), `Checkbox`, `Switch`, `Radio`, `Slider`, `Tooltip` (hover/focus, no pointer-events trap), `Popover`, `Menu`/`DropdownMenu`, `Modal`/`Dialog` (shared primitive — replace ConfirmDialog internals + ShortcutHelpOverlay + any ad-hoc modals; focus trap, Esc, backdrop), `Drawer`, `Tabs`, `SegmentedControl`, `Badge`/`Chip` (status + workflow variants), `Avatar` (initials, color-from-identity), `EmptyState` (icon/title/body/action; replace ad-hoc `.empty-state` text), `ErrorState` (+ retry), `Skeleton` (unify the three existing inline-styled components into token-driven ones), `Spinner`, `Toast` (rebuild: token-driven, success/error/info/warning, **actionable** — undo/retry slot, queue, aria-live), `Pagination`, `DataTable` (sortable headers, column filters, row selection, sticky header, loading/empty states), `SearchInput` (debounced), `Breadcrumbs`, `Kbd`, `StatCard`/`MetricCard` (title, delta, sparkline slot, tone), `ProgressBar`, `RingGauge` (migrate HealthDashboard's), `FormField` (label/help/error/hint), `CommandPalette`, `NotificationBell` (see G2).

---

## 4. App Shell, IA & Global Behavior (Workstream SH)

### SH1. Topbar (rebuild `App.tsx` topbar, L470-525)
New right-aligned cluster: **Global Search** (open datasets/nodes/images by ID/name; `⌘/Ctrl+K` too) → **Command palette** (palette) → **Theme toggle** (DS2) → **Notification bell** (G2) → **Language switcher** → **Avatar + profile menu** (name, role badge, settings, logout). Keep sync-pending badge and shortcuts help; add a **global connection/offline pill** (WS + network, from existing `useNetworkStatus`/sync stats) — persistent, not just on LiveAnnotate.
- Breadcrumbs in content area for nested dataset views (`Datasets / {name} / Annotate`), driven by route.
- Dataset-context selector moves to topbar when rail is collapsed (already done ≤1024px; make it consistent).

### SH2. Sidebar & IA
- Keep sidebar-first + dataset-centric model (it's sound). Refine: collapsed rail (icons + tooltips) at ≤1024, off-canvas drawer ≤768; group labels; **icons from DS4**; active state = accent bar + tint (already) but tightened to token values.
- Section order reflow by persona journey: **Start** (Dashboard) → **Capture & Data** (Upload, Live Annotate, Datasets, Queue) → **Label** (Annotate, Agri Annotate, Road Seg) → **Quality** (Assign, Review, Dedup) → **Analysis & Fleet** (Road/Agri Analysis, Health, Nodes, Training) → **Export** → **Taxonomies** → Settings in footer.
- Keyboard-first: preserve existing digit shortcuts; add `⌘K` palette; keep `?` help (restyle to the new Modal + grouped shortcut table).

### SH3. Persona-aware home (`DashboardHome`)
Redesign the home into **role-first task surfaces** (not one generic hero):
- **ANNOTATOR:** "Today's work" — assigned queue with progress, streak/daily goal (respectful, not gamified), one-click "Start labeling" into their active dataset, recent saves, offline-pending sync count.
- **QA/ADMIN:** ops overview — queue health (pending/overdue), IAA trend, dataset health rings (keep), top flagged classes, recent review actions.
- **OPERATOR:** fleet status strip, uploads/ingestion recent activity, export pipeline status.
- **FIELD_TECH:** fleet (nodes + health) + datasets, nothing more.
- **BUYER:** (future — keep a clean placeholder state, see OS).
- Keep hero minimal: brand eyebrow ("Malawi field annotation"), title, one-line context, status pills. Keep quick-action groups but retinted per DS tokens; remove non-functional decoration.
- **Onboarding:** replace the 3-step `OnboardingBanner` with a proper **role-aware tour** (4–6 steps, coachmark-style, dismissible, persisted) — annotators get canvas/shortcuts/save; operators get fleet/upload; admins get QA/export.

---

## 5. Surface-by-Surface Redesign (Workstream SU)

Each surface: (1) new layout using DS/primitives, (2) explicit empty/loading/error states, (3) inline styles → tokens, (4) i18n complete. Priority order: annotation surfaces > QA/ops > data > analysis > admin.

### SU1. Annotation workspace — **unification decision (recommended: yes)**
Today two canvas systems exist: `AnnotationCanvas` (bbox, active) and `LabelCanvas` (bbox+polygon+AI+TurboReview integration, **unwired**). **Consolidate onto `LabelCanvas` as THE workspace** (it is richer and already integrates AI-assist, polygons, TurboReview, certified-lock), retire `AnnotationCanvas` + its duplicate ImageSidebar wiring. UX direction (benchmark: CVAT/Labelbox ergonomics):
- **Focus mode:** minimal chrome — a left image navigator (thumbnails, labeled/unlabeled/flagged counts), center canvas at 100% fit + zoom (`defaultZoom` setting), right inspector (class palette, confidence, mask/3D toggles).
- **Keyboard-first labeling:** number-key class palette (as TurboReview has), `N` next unlabeled, save shortcut, `Esc` deselect, `⌫` delete — surfaced in the restyled help overlay.
- **AI assist as a first-class flow:** one "Auto-label page" button; results arrive as **pre-labels** with an accept/dismiss confirmation (per the 2026 platform expectation), not silently applied.
- **Trust chrome:** explicit unsaved/queued indicator (45s rural save), per-image status (pending/queued/saved), sync state pill.
- Polygon/Road-Seg keeps `FabricPolygonManager` + `RoadSegPanel` but restyled to the same shell so both canvases feel like one product.

### SU2. TurboReview — wire it or kill it
**Decision: wire it** into the QA flow (it is the fastest path to the 3D/mask refine work from Phase 11B and the best QA ergonomics in the codebase). Give it the new shell + keyboard palette + refine affordances already built; route it from the QA home and Review page ("Fast review" toggle). If wiring is judged too risky this phase, **do not leave it dead** — integrate its refine capabilities into `ReviewPage` and remove the dead files. (Either path: no dead code at phase end.)

### SU3. Data surfaces
- **DatasetBrowser:** add debounced **search**, type/status **filters**, card metadata (sample count, health score chip, last activity), **create + delete** (with ConfirmDialog), empty state with CTA, and a "resume" affordance for the user's last dataset.
- **UploadPage:** unify 4 capture modes into one tabbed surface with shared dropzone chrome; per-file progress via a shared `FileList` primitive; clearer success/duplicate-skipped messaging; field-friendly contrast in light theme.
- **QueuePage / AdminAssignPage:** shared `DataTable` (sort/filter); assignment cards or table rows with progress bars, priority, overdue chip; create form in a Modal (not a separate screen).
- **LiveAnnotate:** keep the camera chrome but restyle to the shell; make the WS/offline + mirror + 3D chips feel like instrument readouts (mono type), not buttons.

### SU4. QA & analysis surfaces
- **ReviewPage:** replace 29 inline styles with tokens; IAA metrics as StatCards + a shared chart language (recharts, one palette); filmstrip stays; certify/reject via the shared Modal (with reason) — restyle, don't rearchitect.
- **HealthDashboard:** add the missing error/empty states; unify rings/StatCards; chart palette from tokens.
- **RoadAnalysis / AgriAnalysis / Taxonomies:** consistent "report surface" — StatCard row, chart, recommendation panel; taxonomies as **beautiful reference sheets** (class cards with swatch, definition, shortcut hint) instead of plain lists.
- **Training:** job cards with live progress + accuracy sparkline; deployed-model list as cards; create form in Modal.
- **Dedup / Export:** keep the wizard structure, restyle; export format cards already exist and are good raw material; add explicit "what ships" summary (orientation badge, mask/3D fields) per Phase 11 export work.

### SU5. Ops & admin
- **NodeManagementPage:** transform the dense table into a **real fleet console**: status summary strip (online/offline/degraded counts), node cards or rows with category icons (DS4), selected-node detail pane with telemetry sparklines, alerts panel, command runner in a Modal. Keep the 3-col layout; restyle.
- **SettingsPage:** regroup into cards/sections (Appearance / Personal / Operational flags / Dedup defaults / Audit); feature-flag toggles as a clean switch list with descriptions; move theme out (DS2).

### SU6. Login & trust moments
- **LoginPage:** full brand moment — restrained gradient, product name, "Malawi field annotation" eyebrow, privacy/consent trust line, accessible form (labels, focus rings), password-strength meter (keep, restyle), error states. **Bright-light legibility:** default light background option, no reliance on dark-only aesthetics.

---

## 6. Standard Bits Every Serious Platform Has (Workstream ST)

The "standard bits" checklist — implement all, wire where sensible:
1. **Global search** (topbar) — datasets, nodes, images; debounced; keyboard-first; `⌘K`.
2. **Command palette** — actions (navigate, start labeling, sync now, theme), same `⌘K` surface as search or a companion.
3. **Notification center** (bell) — server/user-action notifications (review due, sync failed, export complete, assignment), unread dot, mark-read. Backed by existing audit/events where possible; a small read endpoint is permitted if strictly needed (call out explicitly).
4. **Breadcrumbs** on nested dataset views.
5. **Avatar + profile menu** (name, role, settings, logout) — replaces raw name/email badges.
6. **Empty / loading / error states everywhere** — every list/table/canvas/dashboard: `EmptyState` + `Skeleton` + `ErrorState(retry)`; audit and fix every page (HealthDashboard is the known offender).
7. **Toasts with action + undo** where safe (delete dataset, dismiss auto-label) — rebuild `Toast`.
8. **Confirm dialogs for all destructive actions** (delete dataset, reject with reason, export paywall) via shared `Modal`.
9. **Offline/sync status, global** — persistent pill; pending-count badge already exists, make it clickable → sync panel.
10. **Onboarding tour** (role-aware, §SH3).
11. **PWA polish** — real icons (designed, not placeholders), **favicon**, manifest `theme_color` per theme, offline fallback page, service-worker asset caching tuned for rural links (keep ONNX cache).
12. **Data-saver mode** (`reducedMotion`-like setting "Low data"): disables non-essential animations + auto-loads smaller thumbnails; surfaced in Settings and as a one-tap toggle in the connection pill menu.

---

## 7. Motion & Interaction Language (Workstream MO)

One deliberate system, token-driven, reduced-motion safe:
- **State transitions:** 120ms (hover/active/color), 180ms (show/hide), 260ms (panel/overlay), ease-out; overlay/modal entrances 220ms with slight fade+scale (0.98→1); **no bounce/elastic except the one spring token** reserved for confirm/success moments.
- **Press feedback:** active scale 0.97 on buttons/chips; toggle switches slide 120ms.
- **Progress honesty:** saves/uploads/sync show determinate progress or clear "working…" states; skeleton shimmer exists — make it consistent.
- **Annotator ergonomics:** canvas zoom/pan with smooth transitions; box placement shows live size readout; class change animates box color 120ms; no animation on inference overlay (must stay real-time-stable).
- **Respect `reduced-motion`** (setting exists) — all motion gates behind it.

---

## 8. Accessibility, i18n & Brand (Workstream AX)

### AX1. Accessibility (WCAG 2.2 AA — hard requirement)
- Contrast: validate **all** theme token pairs programmatically (script + jest-axe); fix failing pairs (known: `--text-tertiary`).
- Focus: `--ring` visible on all interactive elements; skip-to-content; logical tab order in canvas/sidebar.
- Keyboard: full operability of every primitive (Select, Menu, Modal focus trap, Tabs arrow-key, DataTable sort/filter, canvas tools); existing shortcut system preserved + documented.
- Touch: ≥44px targets on mobile; pointer-coarse spacing for canvas handles (phase4 has coarse-pointer rules — keep/extend).
- Semantics: landmarks (`nav`, `main`), labels on all fields, `aria-live` toasts, `aria-label` on icon buttons; run jest-axe in CI (add dev-dep + vitest task).
- Language: `lang` attribute synced to current locale.

### AX2. i18n — complete Chichewa coverage (DoD: 100%)
- Finish `ny.json` to parity with `en.json` (**222 missing keys**), translate properly (Chichewa), fix the ~25 hardcoded strings listed in §2.6, incl. the brand literal (keep "EdgeVision" as proper noun, localize surrounding copy).
- Locale-aware date/number formatting (MWK amounts), fallback to `en` only as last resort.

### AX3. Brand & PWA assets
- Design a **favicon** + real **PWA icons** (192/512 + maskable), logo refinement (existing SVG → polished mark), manifest metadata (description, categories, `theme_color` per theme), index.html meta (title/description/OG). Replace placeholder 558-byte icons.

---

## 9. Implementation Sequencing & Acceptance

**Order (each step keeps the app shippable):**
1. **DS** — token rewrite + theme system (all pages keep rendering via existing classes where possible; tokens are swapped in place).
2. **PR** — primitive library + jest-axe harness + Toast/Modal/EmptyState/Skeleton/DataTable/Search; migrate highest-value call sites.
3. **SH** — shell rebuild (topbar search/palette/theme/bell/profile/breadcrumbs/offline pill), sidebar refinement, role-aware home + tour.
4. **SU** — surface pass in priority order (annotation unification, QA, data, ops, analysis, admin, login/trust).
5. **MO/ST/AX** — motion pass, standard-bits completion, a11y audit + i18n parity + brand/PWA.

**Acceptance criteria (phase-level):**
- Design tokens are the single source of truth; ≤20 inline styles repo-wide; duplicate/dead CSS removed; `npm run typecheck` + `npm run build` green.
- All primitives ship with Vitest (render + interaction + jest-axe); no element fails contrast audit in any theme; keyboard-only walkthrough passes on annotate, review, fleet, settings.
- `ny.json` at 100% parity; no hardcoded UI strings.
- No dead/unwired screens (LabelCanvas/TurboReview resolved per §SU2); no emoji-as-icons; favicon + PWA icons real.
- Global search, command palette, notification center, breadcrumbs, avatars, onboarding tour, and full empty/loading/error coverage exist and are wired.
- Behavior honors `reduced-motion` + offline/data-saver modes; existing Phase 9-11 invariants (overlay mirror guard, WYSIWYG capture, no silent RLE/depth) remain intact — add a regression note in the overlay test suite.
- All existing Vitest + pytest suites stay green (frontend-only phase; backend untouched unless a called-out read endpoint is added, which must be covered by a pytest).

**Testing additions:** `jest-axe` (dev-dep) + a11y Vitest; contrast-check script; snapshot-free (prefer behavior tests).

---

## 10. Constraints & Out of Scope

**Constraints:** frontend-only; keep backend contracts stable (one exception: permitted small read endpoints — notifications/global search — each explicitly requested and pytest-covered); no new heavy runtime deps (only `lucide-react` allowed); keep the offline-first/Dexie/45s-save architecture (it is a feature); preserve Phase 9-11 invariants; i18n must never block (fallback `en`); every new string in both locales.

**Out of scope:** backend redesign, data-model changes, new business features (buyer marketplace screens are a clean placeholder only), visual regression screenshot tooling (add as a follow-up phase), translation *quality* review beyond coverage (parity first), performance profiling of the backend.

**Decisions this phase resolves (document in the PR summary):** LabelCanvas/AnnotationCanvas unification (§SU1); TurboReview wiring vs. fold-in (§SU2); icon set choice (§DS4); notification center data source (§ST3).
