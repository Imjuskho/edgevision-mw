# EdgeVision Studio — UI/UX Report

**Date:** August 2026  
**Version:** 0.2.0  
**Platform:** EdgeVision-MW Control Plane — Frontend  
**Stack:** React 19, TypeScript 7, Vite 8, Fabric.js 7, ONNX Runtime Web, i18next, Dexie (IndexedDB), Workbox PWA  

---

## Executive Summary

EdgeVision Studio is a full-featured annotation, review, and data management platform designed for rural Malawi's edge-computing data pipeline. The UI is **mature and well-architected**: 26 routes, 21 page components, 35+ UI components, 17 hooks, bilingual i18n (English/Chichewa), three-theme support (dark/light/high-contrast), offline capability, client-side AI inference, and a custom OKLCH design system.

**Overall score: 7.5/10** — Strong foundations, thoughtful accessibility, some rough edges in consistency and edge cases.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Design System](#2-design-system)
3. [Page-by-Page Analysis](#3-page-by-page-analysis)
4. [Accessibility Audit](#4-accessibility-audit)
5. [Mobile & Responsive Design](#5-mobile--responsive-design)
6. [Internationalization](#6-internationalization)
7. [Offline & Performance](#7-offline--performance)
8. [Issues & Recommendations](#8-issues--recommendations)
9. [Strengths](#9-strengths)

---

## 1. Architecture Overview

### Application Shell
Fixed sidebar (220px) + topbar (48px) + scrollable content (max 1180px, centered). Provider tree: `BrowserRouter → AuthProvider → StudioSettingsProvider → NotificationProvider → ErrorBoundary → UnsavedWorkProvider → ToastProvider → StudioApp`.

### Route Map (26 routes)
| Section | Routes | Pages |
|---------|--------|-------|
| **Dashboard** | `/` | `DashboardHome` (role-personalized) |
| **Datasets** | `/datasets`, `/datasets/:id/*` (10 sub-routes) | Browser, Annotation, Segment, Upload, Health, Dedup, Export, Road Analysis, Agri Analysis, Training, Live Annotate, Turbo Review |
| **Queue & Admin** | `/queue`, `/assign`, `/review` | QueuePage, AdminAssignPage, ReviewPage |
| **Taxonomy** | `/road-taxonomy`, `/agri-taxonomy` | Reference pages |
| **Fleet** | `/nodes`, `/nodes/:nodeId` | NodeManagementPage |
| **Operator** | `/operator`, `/operator/dashboard` | OperatorDashboardPage |
| **Buyer** | `/buyer`, `/buyer/dashboard` | BuyerDashboardPage |
| **Marketplace** | `/marketplace` | MarketplacePage |
| **Subject** | `/subject/:subjectHash` | SubjectPortalPage |
| **Settings** | `/settings` | SettingsPage |
| **Auth** | Login page (not route-guarded) | LoginPage |

### Role System (6 roles)
ADMIN, QA, ANNOTATOR, OPERATOR, BUYER, FIELD_TECH — each role sees a personalized dashboard and has per-view access. `AdminRoute`, `RoleRoute`, and `SessionGate` guard routes.

---

## 2. Design System

### Color Model
**OKLCH** (perceptually uniform) with hue 260 (cool blue-violet) across all neutrals. Modern, well-calibrated choice.

| Element | Dark Theme | Light Theme | High Contrast |
|---------|-----------|-------------|---------------|
| Background | L=0.13 | L=0.98 | #000 |
| Surface | L=0.18 | L=1.0 | #0a0a0a |
| Primary text | L=0.96 | L=0.22 | #fff |
| Accent blue | L=0.68 | L=0.68 | unchanged |

### Spacing
4px base unit. Named steps: `--space-0` (0) through `--space-16` (64px).

### Typography
- **Font:** Inter (system-ui fallback) — excellent for data-dense UIs
- **Scale:** Display 36px → H1 24px → H2 20px → H3 16px → Body 14px → Caption 12px
- **Weights:** Display 700, H1 650, H2/H3 600, Body 400

### Shadows
4-level elevation system using `oklch(0 0 0 / alpha)`: sm(0.24) → md(0.32) → lg(0.4) → xl(0.56).

### Focus Ring
Double-ring pattern: `2px root-bg + 2px accent-blue`. Shown only on `:focus-visible` (keyboard only). Excellent pattern.

### Motion
Fast 120ms / Med 180ms / Slow 260ms. Easing: ease-out and spring-with-overshoot. All GPU-friendly (transform/opacity only).

### Component Library (25+ components)
Button, Input, Badge, Modal, Drawer, Tabs, SegmentedControl, Toast, Tooltip, Breadcrumbs, Avatar, StatCard, ProgressBar, Kbd, DataTable, SearchInput, CommandPalette, NotificationBell, RingGauge, Switch, Checkbox, Popover, Pagination, ConnectionPill, Tour, LabelSelector, Skeleton, Spinner.

All use `.ui-` prefix. Consistent BEM naming. Min-height targets meet WCAG 2.5.8 (32/36/44px).

---

## 3. Page-by-Page Analysis

### 3.1 Login Page
**Layout:** Centered card with SVG logo, decorative background pattern, trust/privacy block.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Visual design | Good | Clean, branded, trust-building |
| Form UX | Good | Show/hide password, password strength meter |
| Error handling | Good | `role="alert"` banner, inline validation |
| Accessibility | Good | `aria-hidden` decorations, `htmlFor`/`id` pairs, `autoComplete` |

**Issues:**
- No "forgot password" flow
- No email verification on register
- Login/register toggle reads like body text, not a clear affordance

### 3.2 Dashboard Home
**Layout:** Hero header with glow effect → role-personalized panels → onboarding (no dataset) or dataset banner + health gauges + quick actions (with dataset).

**UX Score: 8/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Role personalization | Excellent | BUYER sees marketplace, ANNOTATOR sees work queue, QA sees quality metrics, OPERATOR sees fleet |
| Health visualization | Good | 4 RingGauges (overall, completeness, accuracy, consistency) with recommendations |
| Quick actions | Good | 15 workflow-grouped buttons with semantic color-coding |
| Loading states | Fair | No skeleton while health data loads (passed as props) |

**Issues:**
- 15+ quick actions may overwhelm on small screens
- `NaN` shown if health data is incomplete (missing `completeness_pct`)
- `ActionIcon` manually parses SVG path strings — fragile

### 3.3 Annotation Page (Core)
**Layout:** AnnotateWorkspace shell (toolbar + canvas + inspector) → canvas for drawing → pre-label modal → status banner.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Drawing tools | Good | Bbox and polygon modes, tool selector |
| AI assist | Good | Auto-label with pre-label confirmation modal |
| Save resilience | Good | Offline-capable save via `useResilientSave` + Dexie |
| Keyboard shortcuts | Good | Save (Ctrl+S), navigate (arrows), label change, skip-to-unlabeled |
| Navigation | Good | Next/prev image, image counter, "skip to unlabeled" |

**Issues:**
- No undo/redo for box drawing
- `JSON.stringify(boxes)` for dirty detection on every render — O(n) performance concern
- Snapshot comparison pattern is fragile for complex nested objects
- Image pagination doesn't handle missing pages well

### 3.4 Live Annotation Page
**Layout:** Setup screen (source picker) → live workspace (video + overlay + toolbar + inspector sidebar).

**UX Score: 8/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Source selection | Good | Camera and screen share with clear icons |
| Real-time overlay | Good | SVG overlay renders bbox/mask/3D cuboids over video |
| Controls | Good | Model type (5 options), display mode, mirror, auto-save, inference badge |
| Inspector sidebar | Good | Model info, display controls, event list, annotation list |

**Issues:**
- OCR blocked when mirrored — error message could be more prominent
- No explicit FPS control (hardcoded at 2fps)
- Mirror preference is localStorage-only (not synced across devices)
- No visual indicator when AI model is "warming up"
- Auto-save silently fails without a dataset selected

### 3.5 Dataset Browser
**Layout:** Header with search/filter toolbar → filter chips → dataset card grid → create modal → delete dialog.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Search & filter | Good | Debounced search (300ms), chip-based type/status filters |
| Card design | Good | Health badge, quality panel (IAA, PII, consent), image count, relative time |
| Create flow | Good | Modal with name, auto-generated slug ID, source type |
| Resume banner | Good | "Continue labeling" for last-used dataset |

**Issues:**
- Delete shows "delete unavailable" dialog — should be hidden or replaced with archive
- No bulk actions (select multiple, delete, export)
- Sort options not clearly labeled
- 1270+ datasets in test DB create a long scroll (no virtualization)

### 3.6 Fleet Management (Node Management)
**Layout:** Fleet summary header → node card grid → node detail sidebar/modal → telemetry charts.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Node status | Good | Online/offline/degraded indicators, district, category badges |
| Telemetry | Good | Battery, CPU temp, storage, LTE signal charts via Recharts |
| Alerts | Good | Active health alerts with acknowledge action |

**Issues:**
- No map view for geographic node distribution
- 50 nodes with test data — no virtualization for large fleets
- Node detail could show live camera feed preview

### 3.7 Marketplace
**Layout:** Dataset browse grid → detail view → quote generation → license selection.

**UX Score: 6/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Browse | Adequate | Grid of dataset cards with price, status, classes |
| Quote flow | Adequate | POST /datasets/quotes → pricing breakdown |

**Issues:**
- Known TS error: `count` type mismatch in i18n `t()` call (`MarketplacePage.tsx:160`)
- No search/filter on marketplace
- No dataset preview (images, annotations)
- No comparison view between datasets
- Quote generation doesn't show line-item breakdown

### 3.8 Subject Portal (Consent)
**Layout:** Subject lookup → consent history → withdraw action → rewards balance.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Lookup | Good | Hash-based subject lookup, portal token generation |
| History | Good | Consent records with status, purposes, timestamps |
| Withdraw | Good | Opt-out with cascading impact preview |
| Rewards | Good | Mobile airtime reward balance display |

### 3.9 Operator Dashboard
**Layout:** Earnings summary → event feed → alerts list → node status → payouts history.

**UX Score: 7/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Earnings | Good | OTP-based login, daily/weekly/monthly summaries |
| Events | Good | Perception event feed with dwell, confidence-drop events |
| Node status | Good | Quick node health view |

### 3.10 Buyer Dashboard
**Layout:** Subscription info → invoice list → traffic/near-miss/pedestrian/road-condition reports → export triggers.

**UX Score: 6/10**

| Aspect | Rating | Notes |
|--------|--------|-------|
| Reports | Adequate | Traffic report, near-miss heatmap, pedestrian exposure, road condition |
| IDOR protection | Good | Cross-buyer data access properly rejected |

**Issues:**
- Reports appear to be placeholder/empty in production
- No data visualization (charts/graphs) for traffic trends
- No subscription management UI

---

## 4. Accessibility Audit

### Strengths
| Feature | Status | Details |
|---------|--------|---------|
| Skip link | ✅ | Present, positioned off-screen, slides to top on focus |
| Focus ring | ✅ | Consistent double-ring `--ring` pattern, `:focus-visible` only |
| Keyboard navigation | ✅ | Annotation shortcuts, command palette (Ctrl+K) |
| ARIA alerts | ✅ | Error banners use `role="alert"` |
| Target sizes | ✅ | Button min-heights: 32/36/44px (WCAG 2.5.8) |
| Semantic HTML | ✅ | Proper heading hierarchy, `<button>`, `<nav>`, `<main>` |
| Reduced motion | ⚠️ | Class-based (`.reduced-motion`), not media-query-based |
| Low data mode | ✅ | Hides thumbnails, disables shimmer |
| Color contrast (dark) | ✅ | Primary 17:1, secondary 9.5:1 (AAA) |

### Gaps
| Issue | Severity | Details |
|-------|----------|---------|
| No `prefers-reduced-motion` media query | Medium | Requires JS to add `.reduced-motion` class; fails if JS is slow |
| No `forced-colors` support | Medium | `box-shadow` focus ring disappears in Windows High Contrast Mode |
| `--text-muted` contrast (light theme) | Medium | `oklch(0.78)` on `oklch(0.98)` ≈ 4.1:1 — **fails WCAG AA** for normal text |
| `--text-secondary` = `--text-muted` | Low | Both identical (`oklch(0.78)`) — no visual differentiation |
| Canvas annotation accessibility | High | Canvas elements are inherently inaccessible to screen readers |
| Modal focus trap | Low | No visible focus-trap indicator (aria attributes present but no visual cue) |
| ~15 hardcoded hex colors | Low | `#34d399`, `#fb923c`, `#FDD835`, etc. bypass theme system |
| No `aria-live` regions for dynamic content | Low | Toast notifications and live annotation results not announced to screen readers |

---

## 5. Mobile & Responsive Design

### Breakpoints
| Width | Behavior |
|-------|----------|
| >1024px | Full sidebar (220px) + topbar + content |
| ≤1024px | Mobile sidebar (slide-in overlay with backdrop) |
| ≤960px | Annotation workspace inspector drops below canvas |
| ≤768px | Reduced padding, search shrinks, queue cards stack |
| ≤640px | Onboarding compresses, analysis bars stack |

### Mobile Assessment
| Aspect | Rating | Notes |
|--------|--------|-------|
| Navigation | Good | Hamburger menu, slide-in sidebar, backdrop overlay |
| Content reflow | Good | Grid layouts use `auto-fit`/`minmax` for responsive collapse |
| Touch targets | Good | Button min-heights meet 44px (WCAG) for lg variant |
| Annotation canvas | Fair | Mouse/touch dependent — no explicit touch gesture handling |
| Video/live annotation | Fair | Standard WebRTC, but no portrait/landscape adaptation |
| Tables | Good | `.ui-table-wrap` enables horizontal scroll on small screens |

### Missing
- No breakpoint above 1024px for ultra-wide monitors
- No `touch-action` CSS for annotation canvas on tablets
- No orientation lock hint for live annotation (portrait vs landscape)
- Sidebar has no collapsed/rail mode at 1024px — it's all-or-nothing

---

## 6. Internationalization

### Languages
| Language | Code | Coverage | Notes |
|----------|------|----------|-------|
| English | `en` | 100% (~1150 lines) | Default/fallback |
| Chichewa (Nyanja) | `ny` | 100% (~1150 lines) | Malawi's national language |

### Implementation
- **Library:** i18next v26 + react-i18next v17
- **Toggle:** `LanguageSwitcher` component in topbar
- **Persistence:** `localStorage` key `studio_language`
- **Namespaces:** 30+ (common, app, nav, views, canvas, review, health, fleet, etc.)

### Assessment
| Aspect | Rating | Notes |
|--------|--------|-------|
| Coverage | Excellent | Full translations for both languages |
| Namespace organization | Good | Logical separation by feature area |
| Fallback strategy | Good | English as default for missing keys |
| RTL support | N/A | Both English and Chichewa are LTR |
| Locale-specific formatting | Fair | No explicit number/date formatting (relies on `Intl`) |
| Contextual translation | Fair | Some placeholders may not adapt to Chichewa grammar |

---

## 7. Offline & Performance

### Offline Architecture
| Layer | Technology | Purpose |
|-------|-----------|---------|
| IndexedDB queue | Dexie v4 | Queues annotation saves when offline |
| Service worker | Workbox v7 | Caches static assets, API responses |
| Online detection | `useNetworkStatus` | Connection pill in topbar (online/offline/syncing) |
| Resilient save | `useResilientSave` | Retries failed saves, falls back to queue |

### Performance Features
| Feature | Status | Notes |
|---------|--------|-------|
| Lazy loading | ✅ | All page components via `React.lazy()` |
| Code splitting | ✅ | Vite manual chunks: ONNX runtime, Fabric, Recharts, i18n |
| Image optimization | ✅ | `sharp` for icon generation, lazy image loading |
| Canvas rendering | ✅ | Fabric.js with zoom, pan, GPU-accelerated transforms |
| Client-side AI | ✅ | ONNX Runtime Web for YOLOv8-seg inference in browser |
| Skeleton loading | ✅ | `ui-skeleton` components with shimmer animation |
| Low data mode | ✅ | Hides thumbnails, disables shimmer |

### PWA Support
- Service worker registered via `vite-plugin-pwa`
- Offline fallback for static assets
- `manifest.json` with app icons, theme color, display mode
- Workbox runtime caching for ONNX models, studio images, API responses

### Performance Concerns
- `JSON.stringify(boxes)` dirty detection on every render — O(n) per keystroke
- No virtualization for large dataset lists (1270+ datasets)
- No image lazy-loading in annotation sidebar (loads all thumbnails)
- ONNX model loading blocks UI thread (no Web Worker offloading visible)

---

## 8. Issues & Recommendations

### Critical (Fix Immediately)
| # | Issue | Location | Impact |
|---|-------|----------|--------|
| C1 | **`--text-muted` fails WCAG AA on light theme** (~4.1:1) | `studio-tokens.css` | Accessibility regression for light-theme users |
| C2 | **MarketplacePage TS error** (`count` type in `t()`) | `MarketplacePage.tsx:160` | Build warning, potential runtime error |

### High Priority
| # | Issue | Recommendation |
|---|-------|---------------|
| H1 | **No undo/redo in annotation** | Add undo stack (Ctrl+Z/Ctrl+Shift+Z) with 50-entry history |
| H2 | **Canvas inaccessible to screen readers** | Add `aria-label` on canvas, provide list-view alternative for annotations |
| H3 | **No `prefers-reduced-motion` media query** | Replace `.reduced-motion` class with `@media (prefers-reduced-motion: reduce)` |
| H4 | **No forced-colors support** | Add `@media (forced-colors: active)` for focus ring and status colors |
| H5 | **~15 hardcoded hex colors in pages.css** | Replace `#34d399`, `#fb923c`, `#FDD835`, etc. with design tokens |
| H6 | **`JSON.stringify` dirty detection** | Replace with shallow-equal or `useRef` snapshot |
| H7 | **No virtualization for large lists** | Add `react-window` or `@tanstack/virtual` for dataset cards, node lists |

### Medium Priority
| # | Issue | Recommendation |
|---|-------|---------------|
| M1 | **No forgot-password flow** | Add password reset via email or admin |
| M2 | **No dataset preview in marketplace** | Show sample thumbnails and annotation previews |
| M3 | **Delete shows "unavailable" dialog** | Remove delete button or implement archive |
| M4 | **`--text-secondary` = `--text-muted`** | Differentiate values or consolidate |
| M5 | **Duplicate `.reduced-motion` rules** | Deduplicate across `studio-tokens.css` and `pages.css` |
| M6 | **Mixed unit systems** | Standardize on CSS tokens over raw px/rem in pages.css |
| M7 | **No `aria-live` regions** | Add `aria-live="polite"` to toast container and live annotation results |
| M8 | **ONNX loads on main thread** | Offload model inference to Web Worker |
| M9 | **No map view for fleet** | Add Leaflet/MapLibre node location visualization |
| M10 | **Buyer dashboard reports empty** | Populate with real data or remove placeholder |

### Low Priority
| # | Issue | Recommendation |
|---|-------|---------------|
| L1 | **Export accent uses `#34d399`** | Replace with token |
| L2 | **No collapsed sidebar at 1024px** | Add rail mode breakpoint |
| L3 | **No orientation lock for live annotation** | Add landscape recommendation banner |
| L4 | **ActionIcon parses SVG paths manually** | Use `lucide-react` icons consistently |
| L5 | **No bulk dataset actions** | Add multi-select for batch operations |
| L6 | **No ultra-wide breakpoint** | Add `@media (min-width: 1600px)` for wider content |
| L7 | **Modal focus trap not visually indicated** | Add focus outline inside modal panel |

---

## 9. Strengths

| Category | What's Done Well |
|----------|-----------------|
| **Design system** | OKLCH color science, 4px spacing grid, 3-theme support, consistent focus ring |
| **Component library** | 25+ production-quality components with BEM naming, disabled/loading/error states |
| **Accessibility basics** | Skip link, focus-visible, role="alert", keyboard shortcuts, target sizes |
| **i18n** | Full English + Chichewa translations (1150 lines each), 30+ namespaces |
| **Offline support** | Dexie queue + Workbox SW + resilient save + connection pill |
| **Client-side AI** | ONNX Runtime Web for YOLOv8-seg in browser — no server round-trip |
| **Role personalization** | Dashboard adapts to 6 roles with relevant CTAs and metrics |
| **Annotation UX** | Keyboard shortcuts, auto-label, pre-label modal, batch inference |
| **Live annotation** | Real-time camera/screen overlay with 5 model types and display modes |
| **Data pipeline** | Full dataset lifecycle: upload → annotate → review → build → export |
| **Z-index management** | Clean 5-layer scale (90→100→8500→9000→9500→9999) |
| **PWA** | Service worker, manifest, offline caching, icon generation |
| **Consent/privacy** | Subject portal with hash-based lookup, withdraw with cascading impact |
| **Malawi context** | Road taxonomy with 80+ Malawi-specific classes, Chichewa language, district-level fleet |

---

## Appendix: File Inventory

| Category | Count | Key Files |
|----------|-------|-----------|
| Pages | 21 | `LoginPage`, `DatasetBrowser`, `AnnotationPage`, `LiveAnnotatePage`, `NodeManagementPage`, etc. |
| Routes | 26 | Defined in `AppRoutes.tsx` |
| UI components | 39 | `components/ui/` (Button, Modal, Toast, DataTable, etc.) |
| Feature components | 15 | `AnnotationOverlay`, `DashboardHome`, `DedupPanel`, `ExportPreview`, etc. |
| Hooks | 17 | `useAuth`, `useLiveAnnotation`, `useAIAssist`, `useOfflineSync`, etc. |
| Utils | 19 | `roles`, `orientation`, `cameraManager`, `reviewRefine`, etc. |
| CSS files | 10 | `studio-tokens`, `base`, `primitives`, `layout`, `pages`, etc. |
| i18n | 2 languages × 30+ namespaces | ~1150 lines each for `en` and `ny` |
| AI modules | 4 | `yoloSeg.ts`, `onnxManager.ts`, `taxonomyMapping.ts` |
| Types | 470 lines | `types/index.ts` covering all domain interfaces |
| Tests | 43 (frontend) | 10 test files, all passing |

---

*Report generated from source code analysis, live server testing, and automated test results.*
