import { Suspense, useState, useEffect, useCallback, useRef, useMemo } from "react";
import { BrowserRouter, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { useOfflineSync } from "./hooks/useOfflineSync";
import { useToast } from "./components/Toast";
import LoginPage from "./pages/LoginPage";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useKeyboardShortcuts } from "./components/KeyboardShortcuts";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { ShortcutHelpOverlay } from "./components/ShortcutHelpOverlay";
import { AppBreadcrumbs } from "./components/shell/AppBreadcrumbs";
import { GlobalSearchDialog } from "./components/shell/GlobalSearchDialog";
import {
  ConnectionPill,
  IconButton,
  Kbd,
  NotificationBell,
  ProfileMenu,
  Select,
  ThemeToggle,
  type CommandItem,
} from "./components/ui";
import { NotificationProvider, useNotifications } from "./context/NotificationContext";
import { useGlobalSearch } from "./hooks/useGlobalSearch";
import { buildPath, buildPathForDatasetSwitch, DATASET_SCOPED_VIEWS, parsePath, SESSION_VIEWS, VIEW_TITLES, type View } from "./routes/paths";
import { clearLastDatasetId, resolveDatasetId, setLastDatasetId } from "./utils/datasetContext";
import { useIsAdmin } from "./routes/AdminRoute";
import { AppRoutes } from "./routes/AppRoutes";
import { RouteFallback } from "./routes/RouteFallback";
import { UnsavedWorkProvider, useUnsavedWork } from "./context/UnsavedWorkContext";
import { StudioSettingsProvider, useStudioSettings } from "./context/StudioSettingsContext";
import { DashboardHome } from "./components/DashboardHome";
import { RoleAwareTour } from "./components/RoleAwareTour";
import { canAccessView } from "./utils/roles";
import { Search } from "lucide-react";

import "./i18n";
import { studioApi } from "./services/api";
import type { GlobalSearchResult } from "./hooks/useGlobalSearch";
import type { HealthScore, Dataset } from "./types";

interface NavItemDef {
  key: View;
  labelKey: string;
  icon: string;
  admin?: boolean;
}

const NAV_SECTION_DEFS: { sectionKey: string; items: NavItemDef[] }[] = [
  {
    sectionKey: "nav.sections.labeling",
    items: [
      { key: "annotate", labelKey: "nav.annotate", icon: "M8 12h8M12 2l10 5-10 5L2 7l10-5z" },
      { key: "agriAnnotate", labelKey: "nav.agriAnnotate", icon: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
      { key: "segment", labelKey: "nav.segment", icon: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
    ],
  },
  {
    sectionKey: "nav.sections.data",
    items: [
      { key: "datasets", labelKey: "nav.datasets", icon: "M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M2 4h20M12 12h.01" },
      { key: "upload", labelKey: "nav.upload", icon: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" },
      { key: "queue", labelKey: "nav.queue", icon: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" },
    ],
  },
  {
    sectionKey: "nav.sections.quality",
    items: [
      { key: "admin", labelKey: "nav.assign", icon: "M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2", admin: true },
      { key: "review", labelKey: "nav.review", icon: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", admin: true },
      { key: "dedup", labelKey: "nav.dedup", icon: "M16 3h5v5M8 3H3v5M12 22V8M21 3l-9 9" },
    ],
  },
  {
    sectionKey: "nav.sections.analysis",
    items: [
      { key: "roadAnalysis", labelKey: "nav.roadAnalysis", icon: "M22 12h-4l-3 9L9 3l-3 9H2" },
      { key: "agriAnalysis", labelKey: "nav.agriAnalysis", icon: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" },
      { key: "health", labelKey: "nav.health", icon: "M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" },
      { key: "fleet", labelKey: "nav.fleet", icon: "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" },
      { key: "liveAnnotate", labelKey: "nav.liveAnnotate", icon: "M15 10l4.553-4.553a2 2 0 00-2.828-2.828L10 7l-5 3-2 6 6-2 5-4z" },
    ],
  },
  {
    sectionKey: "nav.sections.taxonomies",
    items: [
      { key: "roadTaxonomy", labelKey: "nav.roadTaxonomy", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" },
      { key: "agriTaxonomy", labelKey: "nav.agriTaxonomy", icon: "M7 21h10M12 3v18M3 7l9-4 9 4" },
    ],
  },
  {
    sectionKey: "nav.sections.trainExport",
    items: [
      { key: "training", labelKey: "nav.training", icon: "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18" },
      { key: "export", labelKey: "nav.export", icon: "M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" },
    ],
  },
];

function StudioApp() {
  const { t } = useTranslation();
  const { isAuthenticated, logout, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const parsed = parsePath(location.pathname);
  const { view, nodeId } = parsed;
  const datasetId = parsed.datasetId || "";
  const navigationDatasetId = resolveDatasetId(parsed.datasetId);
  const isAdmin = useIsAdmin();
  const { confirmLeaveIfNeeded } = useUnsavedWork();
  const { isViewEnabled, showDashboardHealth, settings, updatePersonal } = useStudioSettings();
  const { notifications, markRead, markAllRead, addNotification } = useNotifications();

  const [sessionId, setSessionId] = useState("");
  const [sessionDatasetId, setSessionDatasetId] = useState("");
  const [imageIndex, setImageIndex] = useState(0);
  const [health, setHealth] = useState<HealthScore | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(false);
  const [datasetsError, setDatasetsError] = useState(false);
  const [datasetsPage, setDatasetsPage] = useState(1);
  const [datasetsPages, setDatasetsPages] = useState(1);
  const [datasetsTotal, setDatasetsTotal] = useState(0);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [shortcutHelpOpen, setShortcutHelpOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const datasetsPageSize = 20;
  const datasetFiltersRef = useRef<{ search?: string; status?: string }>({});
  const globalSearch = useGlobalSearch({ datasets, activeDatasetId: datasetId });

  const navSections = useMemo(
    () =>
      NAV_SECTION_DEFS.map((section) => ({
        section: t(section.sectionKey),
        items: section.items
          .filter((item) => canAccessView(user?.role, item.key))
          .filter((item) => isViewEnabled(item.key))
          .map((item) => ({
            ...item,
            label: t(item.labelKey),
          })),
      })).filter((section) => section.items.length > 0),
    [t, isViewEnabled, user?.role],
  );

  const effectiveSessionId = sessionDatasetId === datasetId ? sessionId : "";

  const { isOnline, stats, triggerSync } = useOfflineSync(effectiveSessionId || "");
  const { showToast } = useToast();
  const prevFailedRef = useRef(0);
  const prevOfflineRef = useRef(isOnline);
  const healthDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadDatasets = useCallback(
    async (page = 1, append = false, filters?: { search?: string; status?: string }) => {
      setDatasetsLoading(true);
      setDatasetsError(false);
      try {
        const resp = await studioApi.listDatasets({
          page,
          page_size: datasetsPageSize,
          search: filters?.search,
          status: filters?.status,
        });
        const items = resp.data?.items || resp.data;
        const list = Array.isArray(items) ? items : [];
        setDatasets((prev) => (append ? [...prev, ...list] : list));
        setDatasetsPage(page);
        setDatasetsPages(resp.data?.pages || 1);
        setDatasetsTotal(resp.data?.total ?? list.length);
      } catch {
        setDatasetsError(true);
        showToast("Failed to load datasets", "error");
      } finally {
        setDatasetsLoading(false);
      }
    },
    [datasetsPageSize, showToast],
  );

  const refreshDatasets = useCallback(
    (filters?: { search?: string; status?: string }) => {
      datasetFiltersRef.current = filters ?? {};
      void loadDatasets(1, false, filters);
    },
    [loadDatasets],
  );

  useEffect(() => {
    if (isAuthenticated) loadDatasets(1, false);
  }, [isAuthenticated, loadDatasets]);

  const loadMoreDatasets = useCallback(async () => {
    if (datasetsLoading || datasetsPage >= datasetsPages) return;
    await loadDatasets(datasetsPage + 1, true, datasetFiltersRef.current);
  }, [datasetsLoading, datasetsPage, datasetsPages, loadDatasets]);

  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  const navigateToView = useCallback(
    (v: View) => {
      void (async () => {
        if (SESSION_VIEWS.includes(view)) {
          const ok = await confirmLeaveIfNeeded(effectiveSessionId);
          if (!ok) return;
        }
        closeMobileNav();
        const activeDatasetId = navigationDatasetId;
        if (
          DATASET_SCOPED_VIEWS.includes(v) &&
          v !== "home" &&
          v !== "datasets" &&
          !activeDatasetId
        ) {
          showToast(t("app.selectDatasetFirst"), "info");
          navigate("/datasets");
          return;
        }
        if (!isViewEnabled(v)) {
          showToast(t("settings.featureDisabled", "This feature is disabled in Settings."), "info");
          navigate("/settings");
          return;
        }
        navigate(buildPath(v, { datasetId: activeDatasetId || undefined, nodeId }));
      })();
    },
    [navigate, navigationDatasetId, nodeId, view, effectiveSessionId, confirmLeaveIfNeeded, closeMobileNav, showToast, t, isViewEnabled],
  );

  const onSessionReady = useCallback((sid: string, dsId: string) => {
    setSessionId(sid);
    setSessionDatasetId(dsId);
  }, []);

  const handleSelectDataset = useCallback(
    (dsId: string) => {
      void (async () => {
        if (!dsId) {
          if (SESSION_VIEWS.includes(view)) {
            const ok = await confirmLeaveIfNeeded(effectiveSessionId);
            if (!ok) return;
          }
          clearLastDatasetId();
          setSessionId("");
          setSessionDatasetId("");
          navigate("/");
          return;
        }
        setLastDatasetId(dsId);
        if (dsId === datasetId) return;
        if (SESSION_VIEWS.includes(view)) {
          const ok = await confirmLeaveIfNeeded(effectiveSessionId);
          if (!ok) return;
        }
        navigate(buildPathForDatasetSwitch(view, parsed, dsId));
        closeMobileNav();
      })();
    },
    [navigate, view, parsed, datasetId, effectiveSessionId, confirmLeaveIfNeeded, closeMobileNav],
  );

  useEffect(() => {
    if (stats.failed > prevFailedRef.current) {
      addNotification({
        title: t("sync.failedTitle", "Sync failed"),
        body: t("sync.failedBody", "{{count}} items need attention", { count: stats.failed }),
      });
    }
    prevFailedRef.current = stats.failed;
  }, [stats.failed, addNotification, t]);

  useEffect(() => {
    if (prevOfflineRef.current && !isOnline) {
      addNotification({
        title: t("nav.offline", "Offline"),
        body: t("sync.offlineBody", "Changes will queue until you're back online."),
      });
    }
    if (!prevOfflineRef.current && isOnline && stats.pending > 0) {
      addNotification({
        title: t("sync.backOnline", "Back online"),
        body: t("sync.pending", "{{count}} pending sync", { count: stats.pending }),
      });
    }
    prevOfflineRef.current = isOnline;
  }, [isOnline, stats.pending, addNotification, t]);

  const handleSearchResult = useCallback(
    (result: GlobalSearchResult) => {
      if (result.kind === "dataset") {
        handleSelectDataset(result.id);
        return;
      }
      if (result.kind === "node") {
        navigate(buildPath("fleet", { nodeId: result.id }));
        return;
      }
      if (result.kind === "image") {
        void (async () => {
          const ds = result.datasetId || datasetId;
          if (!ds) {
            showToast(t("app.selectDatasetFirst"), "info");
            return;
          }
          try {
            const resp = await studioApi.listImages(ds, 1, 200);
            const list = (resp.data?.images ?? resp.data ?? []) as { index: number; annotation_id: string }[];
            const match = list.find((img) => img.annotation_id === result.id);
            if (match) setImageIndex(match.index);
            handleSelectDataset(ds);
            navigate(buildPath("annotate", { datasetId: ds }));
          } catch {
            handleSelectDataset(ds);
            navigate(buildPath("annotate", { datasetId: ds }));
          }
        })();
      }
    },
    [handleSelectDataset, navigate, datasetId, showToast, t],
  );

  const loadHealth = useCallback(async () => {
    if (!datasetId) return;
    try {
      const resp = await studioApi.getHealth(datasetId);
      setHealth(resp.data);
      setHealthError(false);
    } catch {
      setHealth(null);
      setHealthError(true);
    }
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId || datasetId.length < 3) {
      setHealth(null);
      setHealthError(false);
      return;
    }
    if (healthDebounceRef.current) clearTimeout(healthDebounceRef.current);
    healthDebounceRef.current = setTimeout(() => loadHealth(), 800);
    return () => {
      if (healthDebounceRef.current) clearTimeout(healthDebounceRef.current);
    };
  }, [datasetId, loadHealth]);

  useEffect(() => {
    if (!SESSION_VIEWS.includes(view)) {
      setSessionId("");
      setSessionDatasetId("");
      setImageIndex(0);
    }
  }, [view]);

  useEffect(() => {
    setImageIndex(0);
  }, [datasetId]);

  const viewTitle = t(`views.${view}`, VIEW_TITLES[view] || view);

  const commandItems = useMemo((): CommandItem[] => {
    const navItems: CommandItem[] = navSections.flatMap((section) =>
      section.items.map((item) => ({
        id: `nav-${item.key}`,
        label: item.label,
        group: section.section,
        onSelect: () => handleNavClickRef.current(item),
      })),
    );
    return [
      ...navItems,
      {
        id: "sync",
        label: t("sync.syncNow", "Sync now"),
        group: t("nav.sections.data", "Data"),
        onSelect: () => triggerSync(),
      },
      {
        id: "settings",
        label: t("nav.settings", "Settings"),
        group: "App",
        onSelect: () => navigate("/settings"),
      },
      {
        id: "shortcuts",
        label: t("shortcuts.title", "Keyboard shortcuts"),
        group: "App",
        shortcut: "?",
        onSelect: () => setShortcutHelpOpen(true),
      },
    ];
  }, [navSections, t, triggerSync, navigate]);

  const handleNavClickRef = useRef<(item: NavItemDef & { label: string }) => void>(() => {});

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useKeyboardShortcuts(
    {
      "?": () => setShortcutHelpOpen((open) => !open),
      "1": () => navigateToView("annotate"),
      "2": () => navigateToView("upload"),
      "3": () => navigateToView("queue"),
      "4": () => {
        if (isAdmin) navigateToView("admin");
        else showToast(t("app.adminOnly"), "info");
      },
      "5": () => {
        if (isAdmin) navigateToView("review");
        else showToast(t("app.adminOnly"), "info");
      },
      "6": () => navigateToView("agriAnnotate"),
      "7": () => navigateToView("segment"),
      "8": () => navigateToView("roadAnalysis"),
      "9": () => navigateToView("fleet"),
      "0": () => navigateToView("training"),
      h: () => navigateToView("health"),
      d: () => navigateToView("dedup"),
      e: () => navigateToView("export"),
      c: () => navigateToView("liveAnnotate"),
      escape: () => {
        void (async () => {
          if (SESSION_VIEWS.includes(view)) {
            const ok = await confirmLeaveIfNeeded(effectiveSessionId);
            if (!ok) return;
          }
          if (view !== "home" || datasetId) {
            navigate(datasetId ? buildPath("home", { datasetId }) : "/");
          }
        })();
      },
    },
    [isAdmin, view, datasetId, navigateToView, navigate, effectiveSessionId, confirmLeaveIfNeeded, showToast, t],
  );

  if (!isAuthenticated) return <LoginPage />;

  const handleNavClick = (item: NavItemDef & { label: string }) => {
    const needsDataset =
      DATASET_SCOPED_VIEWS.includes(item.key) && item.key !== "home" && item.key !== "datasets";
    const activeDatasetId = navigationDatasetId;

    if (needsDataset && !activeDatasetId) {
      showToast(t("app.selectDatasetFirst"), "info");
      navigate("/datasets");
      return;
    }

    if (!canAccessView(user?.role, item.key)) {
      showToast(t("app.accessDenied", "You don't have access to this area."), "info");
      return;
    }

    if (!isViewEnabled(item.key)) {
      showToast(t("settings.featureDisabled", "This feature is disabled in Settings."), "info");
      navigate("/settings");
      return;
    }

    navigateToView(item.key);
  };

  handleNavClickRef.current = handleNavClick;

  const homeContent = (
    <DashboardHome
      datasetId={datasetId}
      datasets={datasets}
      datasetsTotal={datasetsTotal}
      health={health}
      healthError={healthError}
      isOnline={isOnline}
      pendingSync={stats.pending}
      userRole={user?.role}
      userName={user?.full_name || user?.email}
      showDashboardHealth={showDashboardHealth}
      onNavigate={navigateToView}
      onBrowseDatasets={() => navigate("/datasets")}
    />
  );

  return (
    <div className="studio-root">
      <a href="#main-content" className="skip-link">
        {t("app.skipToContent", "Skip to content")}
      </a>
      {mobileNavOpen && (
        <button
          type="button"
          className="mobile-nav-backdrop"
          aria-label="Close navigation menu"
          onClick={closeMobileNav}
        />
      )}
      <aside className={`studio-sidebar${mobileNavOpen ? " mobile-open" : ""}`} data-tour="sidebar">
        <div
          className="sidebar-header"
          onClick={() => {
            void (async () => {
              if (SESSION_VIEWS.includes(view)) {
                const ok = await confirmLeaveIfNeeded(effectiveSessionId);
                if (!ok) return;
              }
              navigate("/");
              setSessionId("");
              setSessionDatasetId("");
            })();
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span>EdgeVision</span>
        </div>

        <div className="sidebar-dataset">
          <select value={datasetId} onChange={(e) => handleSelectDataset(e.target.value)} aria-label={t("nav.selectDataset")}>
            <option value="">— {t("nav.selectDataset")} —</option>
            {datasets.map((ds) => (
              <option key={ds.dataset_id || ds.id} value={ds.dataset_id || ds.id}>
                {ds.name || ds.dataset_id || ds.id}
              </option>
            ))}
          </select>
        </div>

        <nav className="sidebar-nav">
          <button
            className={view === "home" ? "active" : ""}
            onClick={() => (datasetId ? navigate(buildPath("home", { datasetId })) : navigate("/"))}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
            {t("nav.dashboard")}
          </button>

          {navSections.map((section) => (
            <div key={section.section}>
              <div className="nav-section">{section.section}</div>
              {section.items
                .filter((item) => !item.admin || isAdmin)
                .map((item) => (
                  <button
                    key={item.key}
                    className={view === item.key ? "active" : ""}
                    onClick={() => handleNavClick(item)}
                    data-tour={`nav-${item.key === "admin" ? "assign" : item.key}`}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      {item.icon.split("M").filter(Boolean).map((d, i) => (
                        <path key={i} d={`M${d}`} />
                      ))}
                    </svg>
                    {item.label}
                  </button>
                ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            className={`sidebar-settings-btn${view === "settings" ? " active" : ""}`}
            onClick={() => navigate("/settings")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
            {t("nav.settings", "Settings")}
          </button>
          <div className={`offline-badge ${isOnline ? "" : "offline"}`}>
            {isOnline ? t("nav.online") : t("nav.offline")}
          </div>
          <div className="sidebar-footer-row">
            {stats.pending > 0 && (
              <span className="sync-pending-badge" title={t("sync.pending", { count: stats.pending })}>
                {stats.pending}
              </span>
            )}
          </div>
        </div>
      </aside>

      <div className="studio-main">
        <div className="topbar" data-tour="topbar">
          <button
            type="button"
            className="mobile-menu-btn"
            aria-label="Open navigation menu"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <div className="topbar-title">{viewTitle}</div>
          <div className="topbar-actions">
            <button
              type="button"
              className="ui-btn ui-btn--ghost ui-btn--sm topbar-search-trigger"
              onClick={() => setCommandOpen(true)}
              aria-label={t("app.search", "Search")}
            >
              <Search size={16} />
              <span className="text-body-sm">{t("app.search", "Search")}</span>
              <Kbd>⌘K</Kbd>
            </button>
            <Select
              className="topbar-dataset-select"
              value={datasetId}
              options={[
                { value: "", label: `— ${t("nav.selectDataset")} —` },
                ...datasets.map((ds) => ({
                  value: ds.dataset_id || ds.id,
                  label: ds.name || ds.dataset_id || ds.id,
                })),
              ]}
              onChange={handleSelectDataset}
              searchable
              aria-label={t("nav.selectDataset")}
            />
            <ThemeToggle />
            <NotificationBell notifications={notifications} onMarkRead={markRead} onMarkAllRead={markAllRead} />
            <LanguageSwitcher />
            <IconButton
              label={t("shortcuts.title")}
              size="sm"
              onClick={() => setShortcutHelpOpen(true)}
            >
              ?
            </IconButton>
            <ConnectionPill
              isOnline={isOnline}
              pendingSync={stats.pending}
              onSync={triggerSync}
              lowData={settings.personal.lowDataMode}
              onToggleLowData={() => updatePersonal({ lowDataMode: !settings.personal.lowDataMode })}
            />
            {user && (
              <ProfileMenu
                name={user.full_name || user.email}
                email={user.email}
                role={user.role}
                onSettings={() => navigate("/settings")}
                onLogout={logout}
              />
            )}
          </div>
        </div>

        <div className="content-area" id="main-content">
          <div className="content-area__inner">
            <AppBreadcrumbs
              view={view}
              datasetId={datasetId}
              datasets={datasets}
              onNavigate={navigate}
            />
            <RoleAwareTour />
          <ErrorBoundary>
            <Suspense fallback={<RouteFallback />}>
              <AppRoutes
                datasetId={datasetId}
                imageIndex={imageIndex}
                setImageIndex={setImageIndex}
                datasets={datasets}
                datasetsLoading={datasetsLoading}
                datasetsPage={datasetsPage}
                datasetsPages={datasetsPages}
                datasetsTotal={datasetsTotal}
                datasetsError={datasetsError}
                loadDatasets={loadDatasets}
                refreshDatasets={refreshDatasets}
                loadMoreDatasets={loadMoreDatasets}
                handleSelectDataset={handleSelectDataset}
                onSessionReady={onSessionReady}
                loadHealth={loadHealth}
                homeContent={homeContent}
              />
            </Suspense>
          </ErrorBoundary>
          </div>
        </div>
      </div>
      <GlobalSearchDialog
        open={commandOpen}
        onClose={() => setCommandOpen(false)}
        query={globalSearch.query}
        onQueryChange={globalSearch.setQuery}
        results={globalSearch.results}
        loading={globalSearch.loading}
        commands={commandItems}
        onSelectResult={handleSearchResult}
      />
      <ShortcutHelpOverlay
        open={shortcutHelpOpen}
        onClose={() => setShortcutHelpOpen(false)}
        isAdmin={isAdmin}
      />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <StudioSettingsProvider>
          <NotificationProvider>
            <ErrorBoundary>
              <UnsavedWorkProvider>
                <StudioApp />
              </UnsavedWorkProvider>
            </ErrorBoundary>
          </NotificationProvider>
        </StudioSettingsProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
